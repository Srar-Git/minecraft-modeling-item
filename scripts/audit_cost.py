#!/usr/bin/env python3
"""Read-only authoring/declared-export cost inventory with explicit budgets; no FPS prediction."""
import argparse
import json
from pathlib import Path
from audit_model import audit,PROFILES
from item_common import load_json,write_new

def costs(path,profile,assets=None,plan=None):
    data=load_json(Path(path));base=audit(path,profile,assets);plan=plan or {};es=data.get('elements',[]);ids={e.get('uuid') for e in es}
    metrics={'components':base['counts'].get('elements',0),'declared_faces':base['counts'].get('declared_export_faces',0),'texture_pixels':base['texture_pixels'],'textures':len(base['textures']),'inverted_components':base['counts'].get('inverted_elements',0),'partial_alpha_textures':sum(t['partial_alpha_pixels']>0 for t in base['textures'].values())}
    assigned=set();lanes=[]
    for lane in plan.get('lanes',[]):
        members=lane.get('element_ids',[]);frames=lane.get('frames')
        if not members or len(set(members))!=len(members) or not set(members)<=ids or assigned.intersection(members) or type(frames) is not int or frames<1:raise ValueError('Invalid/overlapping explicitly declared template lane')
        assigned.update(members);lanes.append({'name':lane.get('name'),'template_components':len(members),'frames':frames,'baked_components':len(members)*frames})
    if lanes:metrics['estimated_baked_components']=metrics['components']-len(assigned)+sum(x['baked_components'] for x in lanes)
    violations=[]
    for key,limit in plan.get('budgets',{}).items():
        if key not in metrics or type(limit) is not int or limit<0:raise ValueError('Unknown budget metric or invalid limit: '+key)
        if metrics[key]>limit:violations.append({'metric':key,'actual':metrics[key],'limit':limit})
    extras=data.get('unhandled_root_fields',{})
    custom=[k for k in data if any(t in k.lower() for t in ('motion','animation','preview'))]+list(extras)
    return {'metrics':metrics,'declared_template_lanes':lanes,'budget_violations':violations,'within_declared_budgets':not violations if plan.get('budgets') else None,'structural_errors':base['errors'],'dependencies_complete':base['dependencies_complete'],'custom_fields_for_review':custom,'limitations':['Lane estimate assumes the supplied input contains one geometry template per lane; not inferred or verified motion','No arbitrary custom animation expansion, active-state visibility, draw calls, overdraw or FPS measurement','Unknown custom fields require separate inspection; budget pass is not delivery approval']}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('model',type=Path);p.add_argument('--profile',required=True,choices=PROFILES);p.add_argument('--assets-root',type=Path);p.add_argument('--plan',type=Path);p.add_argument('--output',type=Path);a=p.parse_args();r=costs(a.model,a.profile,a.assets_root,load_json(a.plan) if a.plan else None)
    if a.output:write_new(a.output,r)
    print(json.dumps(r,ensure_ascii=False,indent=2));return int(bool(r['structural_errors'] or r['budget_violations']))

if __name__=='__main__':raise SystemExit(main())
