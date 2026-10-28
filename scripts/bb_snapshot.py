#!/usr/bin/env python3
"""Snapshot the selected live project, including unsaved embedded bitmaps, without saving over it."""
import argparse
import hashlib
import json
from pathlib import Path
from bb_client import Client, structured
from item_common import new_bundle, write_new

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--project-id',required=True);p.add_argument('--output',required=True,type=Path);p.add_argument('--url',default='http://localhost:3000/bb-mcp');a=p.parse_args()
    if a.output.exists():p.error('Output must be a new directory')
    code='(()=>{if(!Project || Project.uuid!=='+json.dumps(a.project_id)+')throw Error("Selected project mismatch");const before={uuid:Project.uuid,name:Project.name,path:Project.save_path,saved:Project.saved,mode:Modes.selected.id};const model=Codecs.project.compile({raw:true,bitmaps:true,absolute_paths:false});return {state:before,model,version:Blockbench.version};})()'
    with Client(a.url,max_bytes=128*1024*1024) as client:result=structured(client.tool('risky_eval',{'code':code}))
    def build(stage):
        write_new(stage/'project.bbmodel',result['model'])
        textures=result['model'].get('textures',[])
        report={'source':result['state'],'blockbench':result['version'],'sha256':hashlib.sha256((stage/'project.bbmodel').read_bytes()).hexdigest(),'textures':[{'name':t.get('name'),'embedded':str(t.get('source','')).startswith('data:')} for t in textures],'limitations':['Snapshot is not an exported runtime package','External particle/audio/reference dependencies are not copied','Custom preview render transforms are not baked into editable coordinates','Unregistered custom metadata may be dropped by the codec; preserve original files and mapping sidecars']}
        write_new(stage/'snapshot.json',report);return report
    report=new_bundle(a.output,build);print(json.dumps({'output':str(a.output),'source':report['source'],'textures':len(report['textures'])},ensure_ascii=False))

if __name__=='__main__':main()
