#!/usr/bin/env python3
"""Isolated behavioral tests; creates fixtures only inside TemporaryDirectory."""
import base64
import copy
import json
from pathlib import Path
import tempfile
import unittest
from PIL import Image
from audit_model import audit
from compare_renders import compare_dirs

class ValidatorsTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.r=Path(self.tmp.name)
        self.assets=self.r/'assets';self.tex=self.assets/'test/textures/item'
        self.tex.mkdir(parents=True);Image.new('RGBA',(32,32),(50,130,190,255)).save(self.tex/'a.png')
        self.native={'textures':{'0':'test:item/a'},'elements':[{'from':[0,0,0],'to':[16,16,1],'faces':{'north':{'texture':'#0','uv':[0,0,16,16]}}}]}
    def tearDown(self):self.tmp.cleanup()
    def run_model(self,m,profile='java-26.1',bb=False):
        p=self.r/('model.bbmodel' if bb else 'model.json');p.write_text(json.dumps(m));return audit(p,profile,self.assets)
    def codes(self,report):return {x['code'] for x in report['errors']}
    def test_modern_multi_axis_and_legacy_rejection(self):
        m=copy.deepcopy(self.native);m['elements'][0]['rotation']={'origin':[8,8,8],'x':75,'y':12.5,'z':0}
        self.assertTrue(self.run_model(m)['structural_errors_absent'])
        self.assertIn('multi_axis_notation_profile',self.codes(self.run_model(m,'java-legacy')))
    def test_free_single_angle_vs_legacy_step(self):
        m=copy.deepcopy(self.native);m['elements'][0]['rotation']={'axis':'z','angle':13}
        self.assertTrue(self.run_model(m,'java-1.21.6')['structural_errors_absent'])
        self.assertIn('legacy_angle_step',self.codes(self.run_model(m,'java-legacy')))
    def test_missing_rotation_axis_is_reported(self):
        m=copy.deepcopy(self.native);m['elements'][0]['rotation']={'angle':13}
        self.assertIn('invalid_rotation',self.codes(self.run_model(m)))
    def test_bbox_and_emission(self):
        m=copy.deepcopy(self.native);m['elements'][0]['to'][1]=33;m['elements'][0]['light_emission']=16
        self.assertTrue({'java_coordinate_overflow','invalid_light_emission'}<=self.codes(self.run_model(m)))
    def test_inverted_shell_is_reviewed_without_repair(self):
        m=copy.deepcopy(self.native);m['elements'][0]['from']=[17,17,2];m['elements'][0]['to']=[-1,-1,-1]
        before=copy.deepcopy(m);result=self.run_model(m)
        self.assertEqual(before,m);self.assertTrue(result['structural_errors_absent']);self.assertEqual(result['counts']['inverted_elements'],1)
    def test_texture_missing_and_alias_cycle(self):
        m=copy.deepcopy(self.native);m['textures']['0']='test:item/missing'
        self.assertIn('texture_unresolved',self.codes(self.run_model(m)))
        m['textures']={'0':'#1','1':'#0'}
        self.assertIn('texture_alias_cycle',self.codes(self.run_model(m)))
    def test_texture_object(self):
        m=copy.deepcopy(self.native);m['textures']['0']={'sprite':'test:item/a','force_translucent':True}
        self.assertTrue(self.run_model(m)['structural_errors_absent'])
        self.assertIn('texture_object_profile',self.codes(self.run_model(m,'java-1.21.6')))
    def test_animation_invalid_frame_and_valid_tall_strip(self):
        Image.new('RGBA',(32,64),(50,130,190,255)).save(self.tex/'a.png')
        meta=self.tex/'a.png.mcmeta';meta.write_text(json.dumps({'animation':{'width':32,'height':32,'frames':[0,2]}}))
        self.assertIn('texture_invalid',self.codes(self.run_model(self.native)))
        meta.write_text(json.dumps({'animation':{'width':32,'height':32,'frames':[0,1],'frametime':2}}))
        row=self.run_model(self.native)['textures']['test:item/a'];self.assertEqual(row['frame_count'],2);self.assertEqual(row['duration_ticks'],4)
    def test_bb_per_texture_uv_space(self):
        data=base64.b64encode((self.tex/'a.png').read_bytes()).decode()
        m={'meta':{'model_format':'java_block'},'resolution':{'width':16,'height':16},'textures':[{'uuid':'tex','uv_width':32,'uv_height':32,'source':'data:image/png;base64,'+data}],
           'elements':[{'type':'cube','from':[0,0,0],'to':[16,16,1],'faces':{'north':{'texture':'tex','uv':[0,0,32,32]}}}]}
        result=self.run_model(m,bb=True);self.assertTrue(result['structural_errors_absent']);self.assertNotIn('uv_outside_texture',{x['code'] for x in result['warnings']})
    def test_parent_inheritance(self):
        target=self.assets/'test/models/base.json';target.parent.mkdir(parents=True);target.write_text(json.dumps(self.native))
        result=self.run_model({'parent':'test:base','textures':{'0':'test:item/a'}})
        self.assertTrue(result['structural_errors_absent']);self.assertEqual(result['counts']['elements'],1)
    def test_render_local_error_not_hidden_by_background(self):
        a=self.r/'a';b=self.r/'b';a.mkdir();b.mkdir();im=Image.new('RGBA',(100,100),(32,39,49,255));im.putpixel((50,50),(10,10,10,255));im.save(a/'frame_000.png');im.save(b/'frame_000.png')
        self.assertTrue(compare_dirs(a,b,[32,39,49])['all_pixel_identical'])
        im.putpixel((50,50),(255,10,10,255));im.save(b/'frame_000.png');result=compare_dirs(a,b,[32,39,49]);row=result['samples'][0]
        self.assertFalse(result['all_pixel_identical']);self.assertEqual(row['changed_pixels'],1);self.assertEqual(row['changed_fraction_foreground'],1)
        self.assertGreater(row['foreground_mean_absolute_rgba_error_0_255'],10)
        (b/'frame_000.png').rename(b/'frame_001.png');self.assertFalse(compare_dirs(a,b)['comparison_inputs_valid'])
    def test_render_size_mismatch_fails(self):
        a=self.r/'a';b=self.r/'b';a.mkdir();b.mkdir();Image.new('RGB',(5,5)).save(a/'a.png');Image.new('RGB',(6,5)).save(b/'a.png')
        self.assertFalse(compare_dirs(a,b)['comparison_inputs_valid'])

if __name__=='__main__':unittest.main(verbosity=2)
