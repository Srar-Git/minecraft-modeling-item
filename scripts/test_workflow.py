#!/usr/bin/env python3
"""Behavioral regression fixtures; no user's models, config or live app touched."""
import base64
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from PIL import Image
from item_common import write_new,new_bundle,safe_relative,confined
from outline_builder import outline,KEY
from optimize_model import optimize,covered
from texture_tools import build_texture
from audit_cost import costs
from package_model import package
from bb_client import Client

FACES=('north','south','east','west','up','down')
def fixture(alpha=255):
    b=io.BytesIO();Image.new('RGBA',(16,16),(50,130,190,alpha)).save(b,format='PNG')
    tex={'uuid':'tex','name':'body.png','uv_width':16,'uv_height':16,'source':'data:image/png;base64,'+base64.b64encode(b.getvalue()).decode()}
    def cube(uid,y):
        return {'uuid':uid,'name':uid,'type':'cube','from':[0,y,0],'to':[2,y+2,2],'origin':[0,0,0],'rotation':[0,0,0],'faces':{f:{'texture':'tex','uv':[0,0,4,4]} for f in FACES}}
    return {'meta':{'format_version':'4.10','model_format':'java_block'},'name':'item_skill_test','resolution':{'width':16,'height':16},'elements':[cube('a',0),cube('b',2)],'outliner':['a','b'],'textures':[tex,{**tex,'uuid':'shelltex','render_sides':'front'}]}

class WorkflowTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.model=fixture()
    def tearDown(self):self.tmp.cleanup()
    def spec(self):return {'element_ids':['a'],'texture_uuid':'shelltex','uv':[0,0,4,4],'thickness':0.15}
    def opt(self,model=None,**kwargs):return optimize(model or self.model,{'static_scope':True,'element_ids':['a','b'],'merge_uniform':True,**kwargs},self.root)
    def test_outline_idempotent_and_source_untouched(self):
        original=copy.deepcopy(self.model);m,r=outline(self.model,self.spec());self.assertEqual(original,self.model)
        m2,r2=outline(m,{**self.spec(),'thickness':0.2});self.assertEqual(r['shell_ids'],r2['shell_ids']);self.assertEqual(len(m2['elements']),3)
        s=m2['elements'][-1];self.assertEqual(s['from'],[2.2,2.2,2.2]);self.assertEqual(s['to'],[-0.2,-0.2,-0.2]);self.assertEqual(s['light_emission'],15)
        self.assertEqual(m2['elements'][:2],self.model['elements'])
    def test_outline_preserves_unknown_project_fields(self):
        self.model['custom_data']={'owner':'test'};m,_=outline(self.model,self.spec());self.assertEqual(m['custom_data'],self.model['custom_data'])
    def test_outline_roundtrip_requires_mapping_sidecar(self):
        m,_=outline(self.model,self.spec());mapping={'schema':1,'mapping':m.pop(KEY)}
        with self.assertRaises(ValueError):outline(m,self.spec())
        again,_=outline(m,{**self.spec(),'thickness':0.2},mapping)
        self.assertEqual(len(again['elements']),3);self.assertEqual(again[KEY],mapping['mapping'])
    def test_outline_missing_or_reparented_shell_rejected(self):
        m,r=outline(self.model,self.spec());uid=r['shell_ids'][0]
        missing=copy.deepcopy(m);missing['elements'].pop()
        with self.assertRaises(ValueError):outline(missing,self.spec())
        m['outliner'].remove(uid);m['outliner'].append({'uuid':'group','children':[uid]})
        with self.assertRaises(ValueError):outline(m,self.spec())
    def test_outline_rejects_shared_sides_and_negative_source(self):
        with self.assertRaises(ValueError):outline(self.model,{**self.spec(),'texture_uuid':'tex'})
        self.model['elements'][0]['from']=[3,3,3]
        with self.assertRaises(ValueError):outline(self.model,self.spec())
    def test_outline_rejects_bounds_and_bad_emission(self):
        for override in ({'thickness':40},{'light_emission':16},{'thickness':float('nan')},{'uv':[0,0,0,2]}):
            with self.assertRaises(ValueError):outline(self.model,{**self.spec(),**override})
    def test_exact_internal_faces_and_merge(self):
        before=copy.deepcopy(self.model);m,r=self.opt();self.assertEqual(before,self.model)
        self.assertEqual(set(map(tuple,r['removed_faces'])),{('a','up'),('b','down')});self.assertEqual(len(m['elements']),1)
        self.assertEqual(m['elements'][0]['from'],[0,0,0]);self.assertEqual(m['elements'][0]['to'],[2,4,2]);self.assertEqual(m['outliner'],['a'])
        self.assertTrue(all(f['texture']=='tex' for f in m['elements'][0]['faces'].values()))
    def test_alpha_rotation_and_negative_bounds_skipped(self):
        for m in (fixture(100),fixture(),fixture()):
            if m['textures'][0]['source']==self.model['textures'][0]['source']:
                if not hasattr(self,'used_rotate'):m['elements'][0]['rotation']=[0,20,0];self.used_rotate=True
                else:m['elements'][0]['from']=[3,3,3]
            candidate,r=self.opt(m);self.assertEqual(candidate,m);self.assertFalse(r['removed_faces'])
    def test_different_parent_groups_not_culled(self):
        self.model['outliner']=[{'uuid':'g1','children':['a']},{'uuid':'g2','children':['b']}]
        m,r=self.opt();self.assertFalse(r['removed_faces']);self.assertEqual(len(m['elements']),2)
    def test_static_declaration_and_animation_rejection(self):
        with self.assertRaises(ValueError):self.opt(static_scope=False)
        self.model['animations']=[{'name':'test'}]
        with self.assertRaises(ValueError):self.opt()
    def test_external_uuid_reference_prevents_merge(self):
        self.model['collections']=[{'children':['b']}]
        with self.assertRaises(ValueError):self.opt()
    def test_nonuniform_texture_not_merged(self):
        b=io.BytesIO();im=Image.new('RGBA',(16,16),'red');im.putpixel((1,1),(0,0,255,255));im.save(b,format='PNG');self.model['textures'][0]['source']='data:image/png;base64,'+base64.b64encode(b.getvalue()).decode()
        m,r=self.opt();self.assertEqual(len(r['removed_faces']),2);self.assertEqual(len(m['elements']),2)
    def test_rectangle_union_requires_complete_coverage(self):
        self.assertTrue(covered((0,0,4,4),[(0,0,2,4),(2,0,4,4)]));self.assertFalse(covered((0,0,4,4),[(0,0,1.99,4),(2,0,4,4)]))
    def image(self,name,color='red',size=(4,4)):
        Image.new('RGBA',size,color).save(self.root/name)
    def texture(self,spec):return new_bundle(self.root/'out',lambda p:build_texture(spec,self.root,p))
    def test_frame_dedup_preserves_timeline(self):
        self.image('a.png');self.image('b.png');self.image('c.png','blue')
        r=self.texture({'mode':'frames','files':['a.png','b.png','c.png'],'timeline':[{'index':1,'time':3},{'index':2,'time':2},{'index':0,'time':4}]})
        self.assertEqual(r['stored_frames'],2);self.assertEqual(r['ticks'],9)
        meta=json.loads((self.root/'out/texture.png.mcmeta').read_text());self.assertEqual(meta['animation']['frames'],[{'index':0,'time':3},{'index':1,'time':2},{'index':0,'time':4}])
    def test_atlas_exact_rgba_and_dedup(self):
        self.image('a.png',(10,20,30,60));self.image('b.png',(10,20,30,60))
        r=self.texture({'mode':'atlas','files':['a.png','b.png'],'width':16});self.assertEqual(r['unique_tiles'],1)
        with Image.open(self.root/'out/texture.png') as im:self.assertEqual(im.crop(r['pixel_rects']['a.png']).tobytes(),Image.open(self.root/'a.png').tobytes())
    def test_texture_failure_publishes_nothing(self):
        self.image('a.png');self.image('b.png',size=(5,5))
        with self.assertRaises(ValueError):self.texture({'mode':'frames','files':['a.png','b.png']})
        self.assertFalse((self.root/'out').exists())
    def test_no_clobber_or_path_escape(self):
        p=self.root/'keep';write_new(p,b'old')
        with self.assertRaises(FileExistsError):write_new(p,b'new')
        self.assertEqual(p.read_bytes(),b'old')
        for s in ('../escape','/absolute','a/../b','a//b','a\\b',None):
            with self.assertRaises(ValueError):safe_relative(s)
        (self.root/'outside').symlink_to(self.root.parent,target_is_directory=True)
        with self.assertRaises(ValueError):confined(self.root,'outside/no')
    def test_explicit_cost_budget_and_lane_estimate(self):
        p=self.root/'a.bbmodel';write_new(p,self.model)
        r=costs(p,'java-26.1',plan={'lanes':[{'name':'one','element_ids':['a'],'frames':20}],'budgets':{'components':1,'estimated_baked_components':21}})
        self.assertEqual(r['metrics']['estimated_baked_components'],21);self.assertEqual(len(r['budget_violations']),1)
        self.assertIsNone(costs(p,'java-26.1')['within_declared_budgets'])
        with self.assertRaises(ValueError):costs(p,'java-26.1',plan={'lanes':[{'element_ids':['a'],'frames':2},{'element_ids':['a'],'frames':3}]})
    def packspec(self):
        self.image('tex.png');contents={'pack.mcmeta':{'pack':{'pack_format':84,'description':'test'}},'assets/test/models/item/a.json':{'textures':{'0':'test:item/a'},'elements':[{'from':[0,0,0],'to':[2,4,2],'faces':{'north':{'texture':'#0','uv':[0,0,16,16]}}}]},'assets/test/items/a.json':{'model':{'type':'minecraft:model','model':'test:item/a'}}}
        for name,data in contents.items():write_new(self.root/name,data)
        target=self.root/'assets/test/textures/item/a.png';target.parent.mkdir(parents=True);target.write_bytes((self.root/'tex.png').read_bytes())
        names=list(contents)+['assets/test/textures/item/a.png']
        return {'profile':'java-26.1','pack_format':84,'files':[{'path':n,'sha256':hashlib.sha256((self.root/n).read_bytes()).hexdigest()} for n in names]}
    def test_package_checks_dependencies_hashes_and_zip(self):
        spec=self.packspec();r=new_bundle(self.root/'bundle',lambda p:package(spec,self.root,p));self.assertEqual(len(r['model_reports']),1)
        with zipfile.ZipFile(self.root/'bundle/resourcepack.zip') as z:self.assertIsNone(z.testzip());self.assertEqual(len(z.namelist()),4)
    def test_package_rejects_stale_hash_and_missing_texture(self):
        spec=self.packspec();bad=copy.deepcopy(spec);bad['files'][0]['sha256']='bad'
        with self.assertRaises(ValueError):new_bundle(self.root/'bad',lambda p:package(bad,self.root,p))
        self.assertFalse((self.root/'bad').exists());spec['files'].pop()
        with self.assertRaises(ValueError):new_bundle(self.root/'bad',lambda p:package(spec,self.root,p))
    def test_mcp_sse_id_and_remote_boundaries(self):
        stream=b'data: {"method":"notify"}\n\ndata: {"id":2,"result":{"ok":true}}\n\n'
        self.assertEqual(Client.decode(stream,'text/event-stream',2),{'ok':True})
        with self.assertRaises(ValueError):Client.decode(stream,'text/event-stream',3)
        with self.assertRaises(ValueError):Client('http://example.com/bb-mcp')
        with self.assertRaises(ValueError):Client.decode(b'{"id":4,"result":{}}','application/json',2)

if __name__=='__main__':unittest.main(verbosity=2)
