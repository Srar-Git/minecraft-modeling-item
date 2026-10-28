#!/usr/bin/env python3
"""Deterministic palette, lossless whole-tile atlas, or animation-strip assembly. No automatic model UV rewrite."""
import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image,ImageColor
from item_common import load_json,confined,new_bundle,write_new

def positive(v,label,limit=4096):
    if type(v) is not int or not 1<=v<=limit:raise ValueError(label+' must be a positive bounded integer')
    return v

def build_texture(spec, root, stage):
    mode=spec.get('mode');report={'mode':mode,'resampled':False}
    if mode=='palette':
        colors=spec.get('colors',{});cell=positive(spec.get('cell',4),'cell',64);cols=positive(spec.get('columns',8),'columns',64)
        if not isinstance(colors,dict) or not 1<=len(colors)<=256:raise ValueError('1..256 named colors required')
        image=Image.new('RGBA',(cols*cell,((len(colors)+cols-1)//cols)*cell));rects={}
        for i,(name,value) in enumerate(colors.items()):
            x=i%cols*cell;y=i//cols*cell;image.paste(ImageColor.getcolor(value,'RGBA'),(x,y,x+cell,y+cell));rects[name]=[x,y,x+cell,y+cell]
        report['pixel_rects']=rects
    elif mode in ('atlas','frames'):
        files=spec.get('files',[])
        if not isinstance(files,list) or not 1<=len(files)<=512 or len(set(files))!=len(files):raise ValueError('1..512 unique input filenames required; reuse timeline indices for repeated frames')
        images=[];total_pixels=0
        for f in files:
            path=confined(root,f)
            with Image.open(path) as src:
                total_pixels+=src.width*src.height
                if total_pixels>16_777_216:raise ValueError('Combined inputs exceed pixel budget')
                images.append(src.convert('RGBA'))
        if mode=='frames':
            size=images[0].size
            if any(im.size!=size for im in images):raise ValueError('Frame sizes differ; no resampling allowed')
            timeline=spec.get('timeline',[{'index':i,'time':1} for i in range(len(images))])
            if not isinstance(timeline,list) or not 1<=len(timeline)<=10000:raise ValueError('Invalid timeline')
            unique=[];lookup={};remap={}
            for i,im in enumerate(images):
                pixels=im.tobytes()
                if pixels not in lookup:lookup[pixels]=len(unique);unique.append(im)
                remap[i]=lookup[pixels]
            frames=[]
            for entry in timeline:
                index=entry.get('index');duration=entry.get('time',1)
                if type(index) is not int or not 0<=index<len(images):raise ValueError('Frame index out of range')
                frames.append({'index':remap[index],'time':positive(duration,'frame time',100000)})
            if size[0]*size[1]*len(unique)>16_777_216:raise ValueError('Output exceeds pixel budget')
            image=Image.new('RGBA',(size[0],size[1]*len(unique)))
            for i,im in enumerate(unique):image.paste(im,(0,i*size[1]))
            write_new(stage/'texture.png.mcmeta',{'animation':{'width':size[0],'height':size[1],'interpolate':False,'frames':frames}})
            report.update(frame_size=list(size),stored_frames=len(unique),timeline_entries=len(frames),ticks=sum(f['time'] for f in frames),input_frame_to_stored=remap)
        else:
            width=positive(spec.get('width',256),'atlas width');padding=positive(spec.get('padding',1),'padding',32)
            x=y=padding;rowh=0;placements=[];dedupe={};rects={}
            for name,im in zip(files,images):
                key=(im.size,im.tobytes())
                if key in dedupe:rects[name]=dedupe[key];continue
                if im.width+2*padding>width:raise ValueError('Tile wider than atlas')
                if x+im.width+padding>width:x=padding;y+=rowh+padding;rowh=0
                rect=[x,y,x+im.width,y+im.height];rects[name]=rect;dedupe[key]=rect;placements.append((im,x,y));x+=im.width+padding;rowh=max(rowh,im.height)
            height=y+rowh+padding
            if height>4096 or width*height>16_777_216:raise ValueError('Atlas exceeds output budget')
            image=Image.new('RGBA',(width,height))
            for im,x,y in placements:image.paste(im,(x,y))
            report.update(pixel_rects=rects,unique_tiles=len(placements),padding=padding,uv_rule='Map pixel rectangles into target logical UV size; preserve mirroring/rotation; no model edited')
    else:raise ValueError('mode must be palette, atlas or frames')
    image.save(stage/'texture.png');report.update(size=list(image.size),pixels=image.width*image.height,sha256=hashlib.sha256((stage/'texture.png').read_bytes()).hexdigest());write_new(stage/'texture.json',report);return report

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('spec',type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args();s=load_json(a.spec)
    r=new_bundle(a.output,lambda stage:build_texture(s,a.spec.parent,stage));print(json.dumps(r,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
