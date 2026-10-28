#!/usr/bin/env python3
"""Create/update managed cuboid shells in a separate bbmodel candidate. No arbitrary contour Boolean operation."""
import argparse
import copy
import json
from pathlib import Path
import uuid
from item_common import load_json,selected_cubes,finite,vector,write_new

KEY='minecraft_item_outline_v1'

def outline(model, spec, managed_map=None):
    if model.get('meta',{}).get('model_format')!='java_block':raise ValueError('Only java_block bbmodel supported')
    chosen=selected_cubes(model,spec.get('element_ids'))
    thickness=spec.get('thickness');uv=spec.get('uv');texture=spec.get('texture_uuid');emission=spec.get('light_emission',15)
    if not finite(thickness) or thickness<=0 or not vector(uv,4) or type(emission) is not int or not 0<=emission<=15:raise ValueError('Positive thickness, UV rectangle and emission 0..15 required')
    ts=[t for t in model.get('textures',[]) if t.get('uuid')==texture]
    if len(ts)!=1:raise ValueError('One existing texture UUID required')
    if ts[0].get('render_sides','auto')!='front':raise ValueError('Use a dedicated front-only outline texture; do not change shared material implicitly')
    size=model.get('resolution',{});w=ts[0].get('uv_width') or size.get('width');h=ts[0].get('uv_height') or size.get('height')
    if not finite(w) or not finite(h) or w<=0 or h<=0 or any(v<0 or v>[w,h][i%2] for i,v in enumerate(uv)) or uv[0]==uv[2] or uv[1]==uv[3]:raise ValueError('Nondegenerate UV rectangle must fit logical texture size')
    layer=spec.get('layer','outer')
    if not isinstance(layer,str) or not layer or len(layer)>64:raise ValueError('Invalid layer key')
    existing=model.get(KEY)
    if managed_map is not None:
        if not isinstance(managed_map,dict) or managed_map.get('schema')!=1 or not isinstance(managed_map.get('mapping'),dict):raise ValueError('Invalid outline mapping sidecar')
        if existing is not None and existing!=managed_map['mapping']:raise ValueError('Embedded and sidecar outline mappings disagree')
        existing=managed_map['mapping']
    if existing is None and any(' / outline ' in e.get('name','') for e in model.get('elements',[])):
        raise ValueError('Possible managed shells without mapping; supply the saved --mapping sidecar after Blockbench roundtrip')
    result=copy.deepcopy(model);mapping=result[KEY]=copy.deepcopy(existing if existing is not None else {})
    if not isinstance(mapping,dict):raise ValueError('Invalid managed outline metadata')
    if any(not isinstance(k,str) or not isinstance(v,str) for k,v in mapping.items()) or len(set(mapping.values()))!=len(mapping):raise ValueError('Invalid or duplicate shell mapping')
    byid={e['uuid']:e for e in result['elements']};generated=[]
    def containers(nodes, source):
        found=[]
        for n in nodes:
            if isinstance(n,str) and n==source:found.append(nodes)
            elif isinstance(n,dict):found.extend(containers(n.get('children',[]),source))
        return found
    for body in chosen:
        if body.get('inflate',0)!=0 or body.get('rescale',False) or any(b<=a for a,b in zip(body['from'],body['to'])):raise ValueError('Reject planes, inverted bounds, inflate and rescale; normalize a separate candidate first')
        if body.get('export') is False or body.get('visibility') is False:raise ValueError('Hidden/non-export body requires explicit manual handling')
        if body['uuid'] in mapping.values():raise ValueError('Cannot outline a managed shell')
        parents=containers(result.get('outliner',[]),body['uuid'])
        if len(parents)!=1:raise ValueError('Source must occur exactly once in outliner')
        key=body['uuid']+':'+layer;old=mapping.get(key)
        if old and old not in byid:raise ValueError('Managed shell missing; repair mapping before retry')
        shell=copy.deepcopy(byid[old]) if old else {}
        shell.update(uuid=old or str(uuid.uuid4()),name=body.get('name','cube')+' / outline '+layer,type='cube',
                     **{'from':[b+thickness for b in body['to']],'to':[a-thickness for a in body['from']],
                        'origin':copy.deepcopy(body.get('origin',[0,0,0])),'rotation':copy.deepcopy(body.get('rotation',[0,0,0])),
                        'inflate':0,'rescale':False,'box_uv':False,'autouv':0,'shade':False,'light_emission':emission,
                        'faces':{f:{'texture':texture,'uv':uv[:],'rotation':0} for f in ('north','south','east','west','up','down')}})
        if any(v<-16 or v>32 for v in shell['from']+shell['to']):raise ValueError('Expanded shell exceeds Java local bounds')
        if old:
            homes=containers(result['outliner'],old)
            if len(homes)!=1 or homes[0] is not parents[0]:raise ValueError('Managed shell no longer shares source parent')
            byid[old].clear();byid[old].update(shell)
        else:result['elements'].append(shell);byid[shell['uuid']]=shell;parents[0].append(shell['uuid'])
        mapping[key]=shell['uuid'];generated.append(shell['uuid'])
    return result,{'shell_ids':generated,'layer':layer,'thickness':thickness,'limitations':['UV must sample a uniform color; gradient contour mapping is manual','Opaque-body occlusion, seams and client culling need visual review','Custom animation membership is not inferred; bind shell IDs to the same track explicitly']}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('model',type=Path);p.add_argument('spec',type=Path);p.add_argument('--mapping',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.suffix!='.bbmodel':p.error('Output must be a new .bbmodel')
    sidecar=Path(str(a.output)+'.outline-map.json')
    if a.output.exists() or sidecar.exists():p.error('Candidate or mapping output already exists')
    result,report=outline(load_json(a.model),load_json(a.spec),load_json(a.mapping) if a.mapping else None)
    write_new(a.output,result);write_new(sidecar,{'schema':1,'mapping':result[KEY]});report['mapping_sidecar']=str(sidecar);print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
