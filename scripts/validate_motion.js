#!/usr/bin/env node
/* Compare actual sampled model-space matrices. Samples must be captured at matched
 * contexts/times by the live driver. This does not execute or certify game animation. */
'use strict';
const fs=require('fs');
function compare(baseline,candidate,tolerance=0) {
  if(!Number.isFinite(tolerance)||tolerance<0) throw Error('Nonnegative explicit tolerance required');
  if(JSON.stringify(baseline.context)!==JSON.stringify(candidate.context))throw Error('Capture contexts differ');
  if(!baseline.context || !Array.isArray(baseline.samples)||!baseline.samples.length||baseline.samples.length!==candidate.samples?.length)throw Error('Nonempty matched samples required');
  let maxError=0,checked=0;const differences=[];
  baseline.samples.forEach((a,index)=>{
    const b=candidate.samples[index];
    if(a.time!==b.time||a.mode!==b.mode)throw Error('Sample time/mode mismatch');
    const keys=Object.keys(a.elements).sort();
    if(!keys.length||JSON.stringify(keys)!==JSON.stringify(Object.keys(b.elements).sort()))throw Error('Element IDs differ');
    for(const key of keys){
      const x=a.elements[key],y=b.elements[key];
      if(!Array.isArray(x)||!Array.isArray(y)||x.length!==16||y.length!==16||!x.every(Number.isFinite)||!y.every(Number.isFinite))throw Error('Expected finite 4x4 matrix');
      let error=0;for(let i=0;i<16;i++)error=Math.max(error,Math.abs(x[i]-y[i]));
      maxError=Math.max(maxError,error);checked++;
      if(error>tolerance)differences.push({sample:index,element:key,max_matrix_component_error:error});
    }
  });
  return {passed:!differences.length,checked_matrices:checked,max_matrix_component_error:maxError,tolerance,differences,limitations:['Only supplied sampled matrices compared; not a vertex, UV, image or FPS comparison','Continuous motion between samples and client runtime remain unverified']};
}
module.exports={compare};
if(require.main===module){
  try {
    const [a,b,tol,out]=process.argv.slice(2);
    if(!a||!b)throw Error('Usage: node validate_motion.js baseline.json candidate.json [tolerance=0] [new-report.json]');
    const r=compare(JSON.parse(fs.readFileSync(a,'utf8')),JSON.parse(fs.readFileSync(b,'utf8')),tol===undefined?0:Number(tol));
    if(out)fs.writeFileSync(out,JSON.stringify(r,null,2)+'\n',{flag:'wx'});
    console.log(JSON.stringify(r,null,2));process.exitCode=r.passed?0:1;
  } catch(e){console.error(e.message);process.exitCode=2;}
}
