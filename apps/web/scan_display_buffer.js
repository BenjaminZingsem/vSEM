/* Frontier-owned acquisition display retention. It never changes native files,
 * exposure,detector counts or scan commands. Missing pixels retain an explicitly
 * older display sample until replaced by an actual acquired prefix. */
(function(root){"use strict";
function finite(v){return typeof v==="number"&&Number.isFinite(v)}
function integer(v,lo,hi){return Number.isSafeInteger(v)&&v>=lo&&v<=hi}
function grid(m){
  if(!m||!integer(m.width_px,1,4096)||!integer(m.height_px,1,4096)||
     !finite(m.field_width_m)||m.field_width_m<=0||!finite(m.offset_x_m)||!finite(m.offset_y_m))throw Error("invalid_display_grid");
  return {width:m.width_px,height:m.height_px,pitch:m.field_width_m/m.width_px,
    x:m.offset_x_m,y:m.offset_y_m};
}
function create(){
  let view=null,counts=null,exposure=null,valid=null,latestOrdinal=-1,latestOrigin=null,fresh=null;
  function allocate(g){view=g;counts=new Uint32Array(g.width*g.height);exposure=new Uint32Array(counts.length);valid=new Uint8Array(counts.length);fresh=new Uint8Array(counts.length)}
  function configure(m){
    const g=grid(m),old=view;
    if(!old){allocate(g);return {cleared:true,reason:"first_grid"}}
    if(old.pitch!==g.pitch){allocate(g);latestOrdinal=-1;latestOrigin=null;return {cleared:true,reason:"pixel_size_changed"}}
    if(old.width===g.width&&old.height===g.height&&old.x===g.x&&old.y===g.y)return {cleared:false,reason:"compatible_grid"};
    // Reframe retained presentation samples when extent changes at equal pitch.
    // These remain old display data,not newly acquired or resampled native files.
    const priorCounts=counts,priorExposure=exposure,priorValid=valid;
    allocate(g);
    for(let y=0;y<g.height;y++)for(let x=0;x<g.width;x++){
      const wx=g.x+(x+.5-g.width/2)*g.pitch,wy=g.y+(g.height/2-y-.5)*g.pitch;
      const px=Math.floor((wx-old.x)/old.pitch+old.width/2),py=Math.floor(old.height/2-(wy-old.y)/old.pitch);
      if(px<0||py<0||px>=old.width||py>=old.height)continue;
      const a=py*old.width+px,b=y*g.width+x;
      counts[b]=priorCounts[a];exposure[b]=priorExposure[a];valid[b]=priorValid[a];
    }
    return {cleared:false,reason:"retained_reframed_grid"};
  }
  function update(m,buffer){
    const g=grid(m),n=g.width*g.height;
    if(!view)throw Error("display_viewport_not_configured");
    if(Object.prototype.toString.call(buffer)!=="[object ArrayBuffer]"||buffer.byteLength!==n*4||
       !integer(m.completed_pixels,0,n)||!integer(m.dwell_ns,1,10000000)||
       !integer(m.active_dwell_ns,0,m.dwell_ns-1)||
       m.completed_pixels===n&&m.active_dwell_ns!==0||
       !integer(m.numerical_verified_ordinal,0,Number.MAX_SAFE_INTEGER)||
       !integer(m.origin_ns,0,Number.MAX_SAFE_INTEGER))throw Error("invalid_acquired_display_cut");
    if(m.numerical_verified_ordinal<latestOrdinal)return {updated:0,ignored:true};
    const data=new DataView(buffer);
    if(m.origin_ns!==latestOrigin){fresh.fill(0);latestOrigin=m.origin_ns}
    latestOrdinal=m.numerical_verified_ordinal;
    const left=view.x-view.width*view.pitch/2,top=view.y+view.height*view.pitch/2;
    const srcLeft=g.x-g.width*g.pitch/2,srcTop=g.y+g.height*g.pitch/2;
    const firstX=Math.max(0,Math.ceil((srcLeft-left)/view.pitch-.5));
    const endX=Math.min(view.width,Math.ceil((srcLeft+g.width*g.pitch-left)/view.pitch-.5));
    const firstY=Math.max(0,Math.ceil((top-srcTop)/view.pitch-.5));
    const endY=Math.min(view.height,Math.ceil((top-srcTop+g.height*g.pitch)/view.pitch-.5));
    let updated=0;
    for(let y=firstY;y<endY;y++)for(let x=firstX;x<endX;x++){
      const column=Math.floor((left+(x+.5)*view.pitch-srcLeft)/g.pitch);
      const row=Math.floor((srcTop-(top-(y+.5)*view.pitch))/g.pitch);
      if(column<0||row<0||column>=g.width||row>=g.height)continue;
      const index=row*g.width+column;
      const duration=index<m.completed_pixels?m.dwell_ns:index===m.completed_pixels?m.active_dwell_ns:0;
      if(duration===0)continue;
      const target=y*view.width+x;
      counts[target]=data.getUint32(index*4,true);exposure[target]=duration;valid[target]=fresh[target]=1;updated++;
    }
    return {updated,ignored:false};
  }
  function pixels(low,high,gamma,brightness,contrast,units){
    if(!view)throw Error("display_viewport_not_configured");
    if(!finite(low)||!finite(high)||low<0||low>=high||!finite(high-low)||
       !finite(gamma)||gamma<.1||gamma>5||!finite(brightness)||brightness< -1||brightness>1||
       !finite(contrast)||contrast<.05||contrast>4||!["counts","cps"].includes(units))throw Error("invalid_display_transfer");
    const result=new Uint8ClampedArray(counts.length*4);
    for(let i=0;i<counts.length;i++){
      let byte=0;
      if(valid[i]){
        const v=units==="counts"?counts[i]:counts[i]*1e9/exposure[i];
        const t=Math.max(0,Math.min(1,((v-low)/(high-low)-.5)*contrast+.5+brightness));
        byte=Math.round(255*Math.pow(t,1/gamma));
      }
      result[i*4]=result[i*4+1]=result[i*4+2]=byte;result[i*4+3]=255;
    }
    return result;
  }
  function snapshot(){
    return view?{width:view.width,height:view.height,pixelPitch:view.pitch,
      counts:counts.slice(),exposure:exposure.slice(),valid:valid.slice(),fresh:fresh.slice()}:null;
  }
  function reset(){view=counts=exposure=valid=fresh=null;latestOrdinal=-1;latestOrigin=null}
  return Object.freeze({configure,update,pixels,snapshot,reset});
}
const api=Object.freeze({create});root.VsemScanDisplayBuffer=api;
if(typeof module!=="undefined"&&module.exports)module.exports=api;
})(typeof globalThis!=="undefined"?globalThis:this);
