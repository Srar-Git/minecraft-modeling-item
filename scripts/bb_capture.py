#!/usr/bin/env python3
"""Capture the live project's current pose from private cameras; does not drive animation or Display slots."""
import argparse
import base64
import json
from pathlib import Path
import uuid
from bb_client import Client, structured
from item_common import load_json,new_bundle,write_new,vector

def image_data(result):
    images=[x for x in result.get('content',[]) if x.get('type')=='image']
    if len(images)!=1 or images[0].get('mimeType')!='image/png':raise ValueError('Expected exactly one PNG image')
    return base64.b64decode(images[0]['data'],validate=True)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('manifest',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--url',default='http://localhost:3000/bb-mcp');a=p.parse_args();m=load_json(a.manifest)
    views=m.get('views',[]);width=m.get('width',768);height=m.get('height',768)
    if not 1<=len(views)<=24 or type(width) is not int or type(height) is not int or not 16<=width<=2048 or not 16<=height<=2048:p.error('1..24 views, width/height 16..2048 required')
    if len({v.get('name') for v in views})!=len(views):p.error('Duplicate view name')
    for v in views:
        if not isinstance(v.get('name'),str) or not v['name'].replace('_','').replace('-','').isalnum() or not vector(v.get('position'),3) or not vector(v.get('target'),3) or v.get('projection') not in ('orthographic','perspective'):p.error('Invalid camera record')
    def build(stage):
        with Client(a.url) as c:
            caps=structured(c.tool('get_capabilities',{}))
            if caps.get('project',{}).get('uuid')!=m.get('project_id'):raise ValueError('Selected project mismatch')
            view_id='item_'+uuid.uuid4().hex[:12];created=False;reports=[];cleanup_warning=None
            try:
                c.tool('create_offscreen_view',{'id':view_id,'width':width,'height':height,'antialias':False,'copy_view':'none'});created=True
                for v in views:
                    if structured(c.tool('get_project_info',{})).get('project',{}).get('uuid')!=m['project_id']:raise ValueError('Project changed during capture')
                    args={k:v[k] for k in ('position','target','projection','zoom','fov') if k in v};args.update(view=view_id,format='png')
                    result=c.tool('set_camera_angle',args);write_new(stage/(v['name']+'.png'),image_data(result));reports.append({'name':v['name'],'requested_camera':args,'applied_view':structured(result).get('view')})
            finally:
                if created:
                    try:c.tool('delete_offscreen_view',{'view':view_id})
                    except RuntimeError as error:
                        # Observed BB 5.2.2: delete releases the preview/context, then
                        # controls.dispose throws. Do not patch shared globals or hide it.
                        if 'onContextMenu is not defined' not in str(error):raise
                        remaining=structured(c.tool('list_views',{})).get('views',[])
                        check=structured(c.tool('risky_eval',{'code':'(()=>({remaining:Preview.all.some(p=>p.id==='+json.dumps('mcp_offscreen_'+view_id)+')}))()'}))
                        if any(v.get('id')==view_id for v in remaining) or check.get('remaining') is not False:raise
                        cleanup_warning='Native cleanup reported onContextMenu is not defined after deletion; absence verified in tool and Preview registries. Controls listener disposal could not be certified.'
            report={'project':caps.get('project'),'blockbench':caps.get('blockbench'),'size':[width,height],'views':reports,'pose_label':m.get('pose_label'),'cleanup_warning':cleanup_warning,'limitations':['Pause/freeze all animation before use; pose_label is caller supplied, not verified','Current editor mode and lighting are inherited; this does not select Display slots','Compare only with captures using identical settings']};write_new(stage/'capture.json',report)
            if cleanup_warning:print('WARNING: '+cleanup_warning)
    new_bundle(a.output,build);print(json.dumps({'output':str(a.output),'views':len(views)}))

if __name__=='__main__':main()
