/* Frontier behavioural audit of a whole source file already inspected as pure
 * arithmetic. VM limits bound an accidental loop;VM is NOT claimed confinement. */
"use strict";
const fs=require("fs"),vm=require("vm");
const source=fs.readFileSync(process.argv[2],"utf8"),cases=JSON.parse(fs.readFileSync(process.argv[3],"utf8"));
const failures=[];
function context(missingShared){
  const c=vm.createContext(missingShared?{SharedArrayBuffer:undefined}:{});
  const before=vm.runInContext("Object.getOwnPropertyNames(globalThis)",c);
  vm.runInContext(source,c,{timeout:10000});
  const after=vm.runInContext("Object.getOwnPropertyNames(globalThis)",c);
  const extra=after.filter(x=>!before.includes(x)&&x!=="VsemIntensityTransfer");
  if(extra.length)failures.push({gate:"unexpected_global_mutations",globals:extra});
  const exports=vm.runInContext("Object.keys(VsemIntensityTransfer).sort()",c);
  if(JSON.stringify(exports)!=='["autoWindow","histogram","render"]')failures.push({gate:"closed_exports",exports});
  return c;
}
function equal(a,b){
  if(typeof a==="number"&&typeof b==="number")return a===b||Math.abs(a-b)<=2e-14*Math.max(Math.abs(a),Math.abs(b),1e-300);
  if(Array.isArray(a)&&Array.isArray(b))return a.length===b.length&&a.every((v,i)=>equal(v,b[i]));
  if(a&&b&&typeof a==="object"&&typeof b==="object")return Object.keys(a).sort().join()==Object.keys(b).sort().join()&&Object.keys(a).every(k=>equal(a[k],b[k]));
  return a===b;
}
const c=context(false);
for(let index=0;index<cases.length;index++){
  c.input=cases[index].input;
  try{
    const actual=vm.runInContext(`(()=>{const d=input,b=new ArrayBuffer(d.counts.length*4),v=new DataView(b);d.counts.forEach((n,i)=>v.setUint32(i*4,n,true));const original=Array.from(new Uint8Array(b));const args=[b,d.width,d.height,d.completed,d.active_ns,d.dwell_ns,d.units],api=VsemIntensityTransfer;const result={histogram:api.histogram(...args,d.bins),autoWindow:api.autoWindow(...args,d.q_low,d.q_high),rgba:Array.from(api.render(...args,d.low,d.high,d.gamma,d.brightness,d.contrast))};if(original.some((n,i)=>new Uint8Array(b)[i]!==n))throw Error("raw_input_mutated");return result})()`,c,{timeout:10000});
    if(!equal(actual,cases[index].expected))failures.push({gate:"independent_math",index,actual,expected:cases[index].expected});
  }catch(error){failures.push({gate:"valid_case_raised",index,error:String(error)})}
}
const isolated=context(true);isolated.input=cases[0].input;
try{vm.runInContext(`(()=>{const d=input,b=new ArrayBuffer(d.counts.length*4);return VsemIntensityTransfer.histogram(b,d.width,d.height,0,0,d.dwell_ns,d.units,4)})()`,isolated,{timeout:10000})}
catch(error){failures.push({gate:"browser_without_SharedArrayBuffer",error:String(error)})}
const rejection=vm.runInContext(`(()=>{const api=VsemIntensityTransfer,b=new ArrayBuffer(16),base=[b,4,1,4,0,20,"counts"],invalid=[];for(const [slot,value] of [[1,true],[2,0],[3,5],[4,20],[5,0],[6,"bad"]]){const args=base.slice();args[slot]=value;invalid.push(args)}invalid.push([new ArrayBuffer(15),4,1,4,0,20,"counts"],[b,4,1,4,1,20,"counts"]);let accepted=0;for(const args of invalid){try{api.histogram(...args,4);accepted++}catch(_){}}const rendering=[[0,0,1,0,1],[0,1,0,0,1],[0,1,1,2,1],[0,1,1,0,0]];for(const args of rendering){try{api.render(...base,...args);accepted++}catch(_){}}return {invalid:invalid.length+rendering.length,accepted}})()`,c,{timeout:10000});
if(rejection.accepted)failures.push({gate:"strict_rejection",...rejection});
console.log(JSON.stringify({status:failures.length?"PRESERVED_INTENSITY_TRANSFER_FAILURE":"PASS_INDEPENDENT_INTENSITY_TRANSFER",
  valid_cases:cases.length,rejection_cases:rejection.invalid,failure_count:failures.length,failures:failures.slice(0,12)}));
process.exitCode=failures.length?2:0;
