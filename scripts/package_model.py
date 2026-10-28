#!/usr/bin/env python3
"""Package an explicit reviewed file manifest, verify hashes/dependencies; never invent a runtime export."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile
from audit_model import audit,PROFILES
from item_common import load_json,confined,safe_relative,new_bundle,write_new

def package(spec,root,stage):
    profile=spec.get('profile');expected=spec.get('pack_format');files=spec.get('files',[])
    if profile not in PROFILES or profile=='generic' or type(expected) is not int or expected<=0:raise ValueError('Explicit Java profile and positive pack_format required')
    if profile=='java-26.1' and expected!=84:raise ValueError('Pinned java-26.1 profile requires pack_format 84; other versions need a verified profile')
    if not files or len({f.get('path') for f in files})!=len(files):raise ValueError('Nonempty unique file manifest required')
    pack=stage/'pack';pack.mkdir();records=[]
    for entry in files:
        name=entry['path'];src=confined(root,name)
        if not src.is_file() or src.is_symlink():raise ValueError('Missing/nonregular manifest file: '+name)
        digest=hashlib.sha256(src.read_bytes()).hexdigest()
        if digest!=entry.get('sha256'):raise ValueError('Stale or absent hash: '+name)
        dest=pack/safe_relative(name);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest);records.append({'path':name,'sha256':digest})
    metadata=load_json(pack/'pack.mcmeta')
    if metadata.get('pack',{}).get('pack_format')!=expected:raise ValueError('pack.mcmeta disagrees with declared pack_format')
    models=sorted((pack/'assets').glob('*/models/**/*.json'));reports=[];unresolved=[]
    if not models:raise ValueError('No Java model JSON in package')
    for model in models:
        r=audit(model,profile,pack/'assets')
        if r['errors']:raise ValueError('Model audit failed: '+str(model.relative_to(pack))+' '+json.dumps(r['errors'])[:1000])
        for warning in r['warnings']:
            if warning['code'] in ('texture_unresolved','parent_unresolved'):unresolved.append(warning['detail'])
        reports.append({'path':str(model.relative_to(pack)),'counts':r['counts'],'warnings':r['warnings']})
    allowed=spec.get('verified_external_resources',[])
    if set(unresolved)-set(allowed):raise ValueError('Unverified external resources: '+repr(sorted(set(unresolved)-set(allowed))))
    # Explicitly review every item-definition leaf, including custom dispatch/condition nodes.
    itemrefs=[]
    def refs(node):
        if isinstance(node,dict):
            if node.get('type') in ('minecraft:model','model'):
                value=node.get('model')
                if not isinstance(value,str):raise ValueError('Item model leaf missing model identifier')
                itemrefs.append(value)
            for v in node.values():refs(v)
        elif isinstance(node,list):
            for v in node:refs(v)
    for path in (pack/'assets').glob('*/items/**/*.json'):refs(load_json(path))
    for ref in itemrefs:
        namespace,name=ref.split(':',1) if ':' in ref else ('minecraft',ref)
        target=confined(pack/'assets',namespace+'/models/'+name+'.json')
        if not target.is_file() and ref not in allowed:raise ValueError('Missing item model leaf: '+ref)
    report={'profile':profile,'pack_format':expected,'files':records,'model_reports':reports,'external_dependencies_acknowledged':sorted(set(unresolved)),'limitations':['No client render/FPS test','No complete item-definition, shader, animation-driver or resource-pack schema validation','Input export is caller supplied; this script does not bake custom bbmodel animation']}
    with zipfile.ZipFile(stage/'resourcepack.zip','w',zipfile.ZIP_DEFLATED) as z:
        for record in records:z.write(pack/record['path'],record['path'])
    with zipfile.ZipFile(stage/'resourcepack.zip') as z:
        if z.testzip():raise ValueError('ZIP integrity failure')
    write_new(stage/'package-report.json',report);return report

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('manifest',type=Path);p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    r=new_bundle(a.output,lambda stage:package(load_json(a.manifest),a.root,stage));print(json.dumps({'output':str(a.output),'files':len(r['files']),'models':len(r['model_reports'])}))

if __name__=='__main__':main()
