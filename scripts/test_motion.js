#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const {compare}=require('./validate_motion');
const matrix=[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1];
const base={context:{project:'fixture',slot:'thirdperson_righthand'},samples:[{time:0,mode:'edit',elements:{cube:matrix}},{time:1,mode:'display',elements:{cube:matrix}}]};
const clone=()=>structuredClone(base);
assert.equal(compare(base,clone()).passed,true);
let other=clone();other.samples[1].elements.cube[12]=0.001;
assert.equal(compare(base,other).passed,false);assert.equal(compare(base,other,0.001).passed,true);
other=clone();other.context.slot='gui';assert.throws(()=>compare(base,other),/contexts/);
other=clone();other.samples[0].time=1;assert.throws(()=>compare(base,other),/time/);
other=clone();other.samples[0].mode='display';assert.throws(()=>compare(base,other),/mode/);
other=clone();other.samples[0].elements={other:matrix};assert.throws(()=>compare(base,other),/IDs/);
other=clone();other.samples[0].elements.cube[0]=NaN;assert.throws(()=>compare(base,other),/finite/);
assert.throws(()=>compare(base,clone(),-1),/tolerance/);
console.log('9 motion comparison assertions passed; live driver is tested separately in Blockbench.');
