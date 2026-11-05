"use strict";
const assert=require("assert"),modulePath=require("path").resolve(__dirname,"../apps/web/scan_display_buffer.js");
const {create}=require(modulePath);
function meta(extra={}){return {width_px:4,height_px:4,field_width_m:4e-6,offset_x_m:0,offset_y_m:0,
  completed_pixels:16,active_dwell_ns:0,dwell_ns:1000,numerical_verified_ordinal:1,origin_ns:10,...extra}}
function raw(values){const b=new ArrayBuffer(values.length*4),v=new DataView(b);values.forEach((x,i)=>v.setUint32(i*4,x,true));return b}
const cases=[];function test(name,run){run();cases.push(name)}
test("new sweep progressively overwrites old display instead of blanking",()=>{
  const d=create(),m=meta();d.configure(m);d.update(m,raw(Array(16).fill(7)));
  d.update(meta({origin_ns:20,numerical_verified_ordinal:2,completed_pixels:2}),raw([0,9,...Array(14).fill(0)]));
  assert.deepStrictEqual(Array.from(d.snapshot().counts),[0,9,...Array(14).fill(7)]);
  assert.deepStrictEqual(Array.from(d.snapshot().fresh),[1,1,...Array(14).fill(0)]);
});
test("only changed viewport pixel pitch clears retained acquisition display",()=>{
  const d=create(),m=meta();d.configure(m);d.update(m,raw(Array(16).fill(7)));
  assert.strictEqual(d.configure(m).cleared,false);assert(d.snapshot().valid.every(x=>x===1));
  assert.strictEqual(d.configure(meta({field_width_m:8e-6})).cleared,true);
  assert(d.snapshot().valid.every(x=>x===0));
});
test("ROI updates a stable survey viewport even with different raster resolution",()=>{
  const d=create(),m=meta();d.configure(m);d.update(m,raw(Array(16).fill(5)));
  d.update(meta({width_px:2,height_px:2,field_width_m:2e-6,completed_pixels:4,
    origin_ns:20,numerical_verified_ordinal:2}),raw([10,11,12,13]));
  assert.strictEqual(d.snapshot().width,4);
  assert.deepStrictEqual(Array.from(d.snapshot().counts),[5,5,5,5,5,10,11,5,5,12,13,5,5,5,5,5]);
});
test("partial active dwell is real display data with its own normalization",()=>{
  const d=create(),m=meta({completed_pixels:0,active_dwell_ns:500});d.configure(m);
  d.update(m,raw([1,...Array(15).fill(0)]));
  assert.strictEqual(d.snapshot().exposure[0],500);
  const pixels=d.pixels(0,2e6,1,0,1,"cps");assert.strictEqual(pixels[0],255);
  assert.strictEqual(pixels[4],0);
});
test("changed display window affects retained samples without changing raw data",()=>{
  const d=create(),m=meta();d.configure(m);const bytes=raw(Array(16).fill(5)),saved=Buffer.from(bytes).toString("hex");
  d.update(m,bytes);assert.strictEqual(d.pixels(0,10,1,0,1,"counts")[0],128);
  assert.strictEqual(d.pixels(0,5,1,0,1,"counts")[0],255);
  assert.strictEqual(Buffer.from(bytes).toString("hex"),saved);
  const detached=d.snapshot();detached.counts.fill(0);assert(d.snapshot().counts.every(x=>x===5));
});
test("late older ordinal cannot overwrite a newer display cut",()=>{
  const d=create(),m=meta({numerical_verified_ordinal:3});d.configure(m);d.update(m,raw(Array(16).fill(5)));
  assert.strictEqual(d.update(meta(),raw(Array(16).fill(99))).ignored,true);
  assert(d.snapshot().counts.every(x=>x===5));
});
test("invalid data is rejected without mutating current retained samples",()=>{
  const d=create(),m=meta();d.configure(m);d.update(m,raw(Array(16).fill(5)));
  for(const bad of [meta({completed_pixels:17}),meta({active_dwell_ns:1}),meta({dwell_ns:true})])
    assert.throws(()=>d.update(bad,raw(Array(16).fill(9))));
  assert(d.snapshot().counts.every(x=>x===5));
  assert.throws(()=>d.pixels(1,0,1,0,1,"counts"));
});
console.log(JSON.stringify({status:"PASS_SCAN_DISPLAY_RETENTION",criteria:cases.length,cases}));
