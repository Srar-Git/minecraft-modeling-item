#!/usr/bin/env python3
"""Conservative candidate optimizer for explicitly selected static, unrotated, opaque cuboids sharing a parent."""
import argparse
import base64
import copy
import io
import json
import math
from pathlib import Path
from PIL import Image
from item_common import load_json,selected_cubes,write_new

FACES={'west':(0,0),'east':(0,1),'down':(1,0),'up':(1,1),'north':(2,0),'south':(2,1)}

def covered(rect,cuts):
    pieces=[rect]
    for x0,y0,x1,y1 in cuts:
        rest=[]
        for a,b,c,d in pieces:
            l=max(a,x0);r=min(c,x1);lo=max(b,y0);hi=min(d,y1)
            if r<=l or hi<=lo:rest.append((a,b,c,d));continue
            if l>a:rest.append((a,b,l,d))
            if r<c:rest.append((r,b,c,d))
            if lo>b:rest.append((l,b,r,lo))
            if hi<d:rest.append((l,hi,r,d))
        pieces=rest
        if not pieces:return True
    return False

def optimize(model,spec,root):
    if model.get('meta',{}).get('model_format')!='java_block' or spec.get('static_scope') is not True:raise ValueError('Requires java_block and explicit static_scope=true')
    if model.get('animations') or model.get('animation_controllers') or model.get('unhandled_root_fields') or any(any(t in k.lower() for t in ('motion','preview')) for k in model):raise ValueError('Animated/custom-runtime project requires a specialized optimizer')
    selected=selected_cubes(model,spec.get('element_ids'))
    if len(selected)>1200:raise ValueError('Scope exceeds 1200 elements; partition into proven independent static groups')
    parents={}
    def walk(nodes,path=()):
        for n in nodes:
            if isinstance(n,str):
                if n in parents:raise ValueError('Duplicate outliner reference')
                parents[n]=path
            elif isinstance(n,dict):walk(n.get('children',[]),path+(n.get('uuid',n.get('name')),))
    walk(model.get('outliner',[]))
    ts=model.get('textures',[]);images={};texmap={}
    for i,t in enumerate(ts):
        for key in (i,str(i),t.get('uuid')):texmap[key]=t
    def face_pixels(e):
        pixels={}
        for side in FACES:
            f=e.get('faces',{}).get(side,{});ref=f.get('texture');t=texmap.get(ref)
            if not t or t.get('render_mode','default')!='default':return None
            source=t.get('source','');key=t.get('uuid',str(ref))
            if key not in images:
                if not source.startswith('data:image/png;base64,'):return None
                images[key]=Image.open(io.BytesIO(base64.b64decode(source.split(',')[1],validate=True))).convert('RGBA')
            im=images[key]
            # Refuse texture animation and non-square images; full strip is not a static opacity proof.
            if im.width!=im.height or t.get('frame_time',1)!=1 or t.get('frame_order') or t.get('frameCount',1)!=1:return None
            uv=f.get('uv');res=model.get('resolution',{});w=t.get('uv_width') or res.get('width',16);h=t.get('uv_height') or res.get('height',16)
            if not isinstance(uv,list) or len(uv)!=4 or not all(isinstance(x,(int,float)) and math.isfinite(x) for x in uv) or w<=0 or h<=0:return None
            x0,x1=sorted([uv[0]*im.width/w,uv[2]*im.width/w]);y0,y1=sorted([uv[1]*im.height/h,uv[3]*im.height/h])
            if x0<0 or y0<0 or x1>im.width or y1>im.height or x0==x1 or y0==y1:return None
            crop=im.crop((math.floor(x0),math.floor(y0),math.ceil(x1),math.ceil(y1)))
            if crop.getchannel('A').getextrema()!=(255,255):return None
            colors=crop.getcolors(1);pixels[side]=colors[0][1] if colors else None
        return pixels
    eligible=[];skipped=[];samples={}
    for e in selected:
        if e['uuid'] not in parents:raise ValueError('Selected element missing from outliner')
        if any(e.get('rotation',[0,0,0])) or e.get('inflate',0) or e.get('rescale',False) or e.get('visibility') is False or e.get('export') is False or any(b<=a for a,b in zip(e['from'],e['to'])):
            skipped.append(e['uuid']);continue
        sample=face_pixels(e)
        if sample is None:skipped.append(e['uuid']);continue
        eligible.append(e);samples[e['uuid']]=sample
    result=copy.deepcopy(model);byid={e['uuid']:e for e in result['elements']};removed_faces=[]
    for e in eligible:
        for side,(axis,positive) in FACES.items():
            u,v=[a for a in range(3) if a!=axis];level=e['to' if positive else 'from'][axis];cuts=[]
            for other in eligible:
                if other is e or parents[other['uuid']]!=parents[e['uuid']]:continue
                if not other['from'][axis]<=level<=other['to'][axis]:continue
                if not (other['to'][axis]>level if positive else other['from'][axis]<level):continue
                cuts.append((other['from'][u],other['from'][v],other['to'][u],other['to'][v]))
            if covered((e['from'][u],e['from'][v],e['to'][u],e['to'][v]),cuts):removed_faces.append((e['uuid'],side))
    for uid,side in removed_faces:byid[uid]['faces'][side]['texture']=None
    removed=set();merged=[]
    if spec.get('merge_uniform'):
        # Conservative vertical merge: same metadata and uniform per-face colors/UVs only.
        for a in eligible:
            if a['uuid'] in removed:continue
            target=byid[a['uuid']]
            for b in eligible:
                if b is a or b['uuid'] in removed or parents[a['uuid']]!=parents[b['uuid']]:continue
                other=byid[b['uuid']]
                if target['to'][1]!=other['from'][1] or any(target[k][axis]!=other[k][axis] for k in ('from','to') for axis in (0,2)):continue
                ignore={'uuid','name','from','to','faces'}
                if {k:v for k,v in target.items() if k not in ignore}!={k:v for k,v in other.items() if k not in ignore}:continue
                if target['faces']['up'].get('texture') is not None or other['faces']['down'].get('texture') is not None:continue
                if any(samples[a['uuid']][f] is None or samples[a['uuid']][f]!=samples[b['uuid']][f] for f in FACES):continue
                if any(target['faces'][f]!=other['faces'][f] for f in ('north','south','east','west')):continue
                target['to'][1]=other['to'][1];target['faces']['up']=copy.deepcopy(other['faces']['up']);removed.add(b['uuid']);merged.append({'kept':a['uuid'],'removed':b['uuid']})
    if spec.get('remove_empty'):
        removed.update(e['uuid'] for e in eligible if all(f.get('texture') is None for f in byid[e['uuid']]['faces'].values()))
    # Do not silently break custom UUID references, collections, or managed outline mappings.
    def references(value):
        if isinstance(value,str):return any(value==uid or (len(uid)>=16 and uid in value) for uid in removed)
        if isinstance(value,dict):return any(references(k) or references(v) for k,v in value.items())
        if isinstance(value,list):return any(references(v) for v in value)
        return False
    if references({k:v for k,v in model.items() if k not in ('elements','outliner')}):raise ValueError('A removed UUID has external project references; preserve it or use a specialized adapter')
    def prune(nodes):
        return [({**n,'children':prune(n.get('children',[]))} if isinstance(n,dict) else n) for n in nodes if not isinstance(n,str) or n not in removed]
    result['elements']=[e for e in result['elements'] if e['uuid'] not in removed];result['outliner']=prune(result.get('outliner',[]))
    return result,{'eligible':len(eligible),'skipped_ids':skipped,'removed_faces':removed_faces,'removed_element_ids':sorted(removed),'merged':merged,'components_before':len(model['elements']),'components_after':len(result['elements']),'limitations':['Only explicitly declared static scope; no animation or arbitrary rotation','Geometric/UV candidate only; same-condition render comparison and actual export still required']}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('model',type=Path);p.add_argument('spec',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.suffix!='.bbmodel':p.error('Output must be new .bbmodel')
    if a.output.exists() or Path(str(a.output)+'.report.json').exists():p.error('Candidate or report output already exists')
    result,report=optimize(load_json(a.model),load_json(a.spec),a.model.parent);write_new(a.output,result);write_new(Path(str(a.output)+'.report.json'),report);print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
