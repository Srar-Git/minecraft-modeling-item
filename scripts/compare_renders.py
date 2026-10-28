#!/usr/bin/env python3
"""Compare matching PNG renders without resizing, camera alignment or editing inputs.
Strict mode fails on any RGBA difference; visual metrics use a supplied flat background.
"""
import argparse
import json
from pathlib import Path
from PIL import Image, ImageChops, ImageStat

def nonzero_mask(image):
    result=Image.new('L',image.size)
    for band in image.split():
        result=ImageChops.lighter(result,band)
    return result.point(lambda x:255 if x else 0)

def compare(before,after,background=None):
    a,b=Image.open(before).convert('RGBA'),Image.open(after).convert('RGBA')
    if a.size!=b.size:
        raise ValueError('Render dimensions differ: '+str(a.size)+' vs '+str(b.size))
    diff=ImageChops.difference(a,b)
    changed=nonzero_mask(diff)
    changed_count=changed.histogram()[255]
    mae=sum(ImageStat.Stat(diff).mean)/4
    mask=None
    if background is not None:
        bg=Image.new('RGBA',a.size,tuple(background)+(255,))
        mask=ImageChops.lighter(nonzero_mask(ImageChops.difference(a,bg)),nonzero_mask(ImageChops.difference(b,bg)))
    foreground_pixels=mask.histogram()[255] if mask else None
    foreground_mae=(sum(ImageStat.Stat(diff,mask).mean)/4 if foreground_pixels else 0) if mask else None
    return {'name':Path(before).name,'size':list(a.size),'changed_pixels':changed_count,
            'changed_bbox':changed.getbbox(),'mean_absolute_rgba_error_0_255':mae,
            'max_channel_error':max(hi for lo,hi in diff.getextrema()),'foreground_pixels':foreground_pixels,
            'foreground_mean_absolute_rgba_error_0_255':foreground_mae,
            'changed_fraction_foreground':changed_count/foreground_pixels if foreground_pixels else None,
            'pixel_identical':changed_count==0}

def compare_dirs(before,after,background=None):
    before,after=Path(before),Path(after)
    a={p.name:p for p in before.glob('*.png')};b={p.name:p for p in after.glob('*.png')}
    errors=[];rows=[]
    if not a or not b:
        errors.append('Both directories must contain PNG renders')
    if a.keys()!=b.keys():
        errors.append({'missing_in_after':sorted(a.keys()-b.keys()),'unexpected_in_after':sorted(b.keys()-a.keys())})
    for name in sorted(a.keys()&b.keys()):
        try:
            rows.append(compare(a[name],b[name],background))
        except Exception as exc:
            errors.append({'name':name,'error':str(exc)})
    return {'comparison_inputs_valid':not errors,'all_pixel_identical':bool(rows) and not errors and all(x['pixel_identical'] for x in rows),
            'background':background,'samples':rows,'errors':errors,
            'limitations':['No perceptual acceptance inferred from small average errors','Only provided PNGs checked; full frame/view coverage must be documented',
                           'Camera, lights, viewport, frame time and renderer settings must match','Transparent hidden RGB differences are included in strict RGBA comparison']}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('before',type=Path);p.add_argument('after',type=Path)
    p.add_argument('--background',help='Flat opaque RGB background, e.g. 32,39,49')
    p.add_argument('--strict',action='store_true',help='Fail on any pixel difference, missing file or size mismatch')
    p.add_argument('--output',type=Path)
    args=p.parse_args()
    bg=None
    if args.background:
        try:
            bg=[int(v) for v in args.background.split(',')]
            if len(bg)!=3 or any(not 0<=v<=255 for v in bg):raise ValueError()
        except ValueError:
            p.error('--background needs three integers in 0..255')
    result=compare_dirs(args.before,args.after,bg)
    data=json.dumps(result,ensure_ascii=False,indent=2)
    if args.output:
        out=args.output.resolve()
        if out.suffix.lower()=='.png':p.error('Output must not overwrite a PNG')
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(data,encoding='utf-8')
    print(data)
    return 0 if result['comparison_inputs_valid'] and (not args.strict or result['all_pixel_identical']) else 1

if __name__=='__main__':raise SystemExit(main())
