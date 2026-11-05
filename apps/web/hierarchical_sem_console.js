(function(){"use strict";
const $=id=>document.getElementById(id),canvas=$("sem-image"),ctx=canvas.getContext("2d");
let csrf=null,state=null,currentImage=null,imageBytes=null,selectedImage="",running=false,refreshing=false,opticsTimer=null;
let pendingRecord=null,desiredViewport=null;
const displayBuffer=VsemScanDisplayBuffer.create(),roiDisplayBuffer=VsemScanDisplayBuffer.create();
const roiCanvas=$("roi-image"),roiContext=roiCanvas.getContext("2d");let roiCutKey=null;
let displayCutKey=null,histogramKey=null,histogramData=null,lastAutoMs=-Infinity,lastAutoOrigin=null,displayFrame=null;
let roi={field_width_m:2e-6,offset_x_m:0,offset_y_m:0},parentImage=null,parentPixels=null;
const stage=VsemStagePoseControls.create($("stage-controls"),action=>stageAction(action));
function error(message){$("error").textContent=message||""}
async function request(path,body){const options=body===undefined?{}:{method:"POST",headers:{"Content-Type":"application/json","X-CSRF-Token":csrf},body:JSON.stringify(body)};const response=await fetch(path,options);if(!response.ok){let data;try{data=await response.json()}catch(_){data={error:"request_failed"}}throw Error(data.error||"request_failed")}return response.json()}
async function waitOperation(receipt){for(let n=0;n<1000;n++){const op=await request("/operation/"+receipt.operation_id);if(["COMPLETED","REJECTED","CANCELLED","UNKNOWN"].includes(op.status)){if(op.status!=="COMPLETED")throw Error(op.reason||op.status);return op}await new Promise(resolve=>setTimeout(resolve,30))}throw Error("completion_unknown")}
async function command(action,parameters={}){if(!state||!state.control_owned)throw Error("Take control first");return request("/command",{action,parameters,expected_stop_generation:state.stop_generation})}
async function sync(){state=await request("/state");updateState();return state}
async function stop(){const op=await command("stop");await waitOperation(op);await sync();running=false;return op}
function scanParameters(width=Number($("live-pixels").value),full=false){return {width_px:width,height_px:width,field_width_m:full?Number($("hfw").value)*1e-6:roi.field_width_m,offset_x_m:full?0:roi.offset_x_m,offset_y_m:full?0:roi.offset_y_m,dwell_ns:Number($(full?"record-dwell":"live-dwell").value)}}
async function live(){await sync();if(state.phase!=="STOPPED")await stop();const parameters=scanParameters();if(parameters.field_width_m===Number($("hfw").value)*1e-6&&parameters.offset_x_m===0&&parameters.offset_y_m===0)desiredViewport={...parameters,minOrigin:state.observed_at_ns||0};await command("scan_live",parameters);running=true;selectedImage="";$("recordings").value=""}
async function record(){await sync();if(state.phase!=="STOPPED")await stop();const parameters=scanParameters(1024,true);roi={field_width_m:parameters.field_width_m,offset_x_m:0,offset_y_m:0};$("roi").style.display="none";desiredViewport={...parameters,minOrigin:state.observed_at_ns||0};const previousImageId=state.latest_image&&state.latest_image.image_id;const receipt=await command("scan_single",parameters);pendingRecord={previousImageId,operationId:receipt.operation_id,previousIds:state.recorded_images.map(m=>m.image_id)};running=false;selectedImage="";updateState()}
async function applyOptics(){const p={current_pA:Number($("beam-current").value),focus_offset_m:Number($("focus").value)*1e-6,stigmator_x:Number($("stig-x").value),stigmator_y:Number($("stig-y").value)};await command("optics",p)}
function scheduleOptics(){clearTimeout(opticsTimer);opticsTimer=setTimeout(()=>applyOptics().catch(e=>error(e.message)),100)}
async function stageAction(action){try{await sync();if(action==="stop")return await stop();let x=state.stage.x_m,y=state.stage.y_m,z=state.stage.z_m;const delta=Number($("hfw").value)*1e-6/4;
if(action==="x-minus")x-=delta;if(action==="x-plus")x+=delta;if(action==="y-minus")y-=delta;if(action==="y-plus")y+=delta;if(action==="z-minus")z-=.5e-6;if(action==="z-plus")z+=.5e-6;
if(action==="move"){x=Number($("target-x").value)*1e-3;y=Number($("target-y").value)*1e-3;z=Number($("target-z").value)*1e-6}
const op=await command("stage_move",{x_m:x,y_m:y,z_m:z});await waitOperation(op);await sync();error("")}catch(e){error(e.message)}}
function nominalScanSeconds(width,dwell){return (.03+width*width*dwell*1e-9+(width-1)*.0001)}
function updateScanReadback(){
const liveWidth=Number($("live-pixels").value),liveDwell=Number($("live-dwell").value),recordDwell=Number($("record-dwell").value);
let text=`Selected live: ${liveWidth}² · ${liveDwell/1000} μs/pixel · ${nominalScanSeconds(liveWidth,liveDwell).toFixed(2)} s nominal\nSelected record: 1024² · ${recordDwell/1000} μs/pixel · ${nominalScanSeconds(1024,recordDwell).toFixed(2)} s nominal`;
if(state.progress)text+=`\nAcquiring: ${state.progress.completed_pixels.toLocaleString()} / ${state.progress.total_pixels.toLocaleString()} pixels · ${(state.progress.elapsed_ns/1e9).toFixed(2)} s elapsed`;
else if(state.phase==="PREPARING")text+="\nPreparing scan response; beam "+(state.beam_blank?"blanked":"active");
else if(pendingRecord)text+="\n"+(state.phase==="STOPPED"?"Physical exposure ended; verifying acquired counts":"Awaiting recording status / verified numerical delivery")+"; beam "+(state.beam_blank?"blanked":"active");
else if(state.phase==="BETWEEN_SWEEPS")text+="\nLive response / delivery pending; beam "+(state.beam_blank?"blanked":"active");
if(currentImage)text+=`\nDisplayed capture: ${currentImage.dwell_ns/1000} μs/pixel · ${(currentImage.cut_elapsed_ns/1e9).toFixed(3)} s · ${currentImage.outcome.toLowerCase()}`;
if(currentImage&&Number.isSafeInteger(state.observed_at_ns))text+=`\nDisplayed cut is ${(Math.max(0,state.observed_at_ns-currentImage.origin_ns-currentImage.cut_elapsed_ns)/1e9).toFixed(2)} s behind observed instrument time`;
$("scan-readback").textContent=text+"\nGeneric timing; accurate numerical delivery may take longer.";
}
function updateState(){if(!state||state.availability!=="AVAILABLE"){if(state)error(state.availability);return}const s=state.stage,owned=state.control_owned;$("phase").textContent=state.phase.replaceAll("_"," ");$("beam").textContent="Beam "+(state.beam_blank?"blanked":"scanning");$("current-stage").textContent=`X ${(s.x_m*1e3).toFixed(6)} · Y ${(s.y_m*1e3).toFixed(6)} mm · Z ${(s.z_m*1e6).toFixed(2)} μm`;$("wd").textContent=`WD ${(s.working_distance_m*1e3).toFixed(4)} mm`;$("latency").textContent=`State ${(state.delivery_age_ns/1e6).toFixed(0)} ms old`;$("control-state").textContent=owned?"Control owned":state.control?"Control held by "+state.control.holder:"No control";
if(pendingRecord&&state.recorded_images.some(m=>!pendingRecord.previousIds.includes(m.image_id)))pendingRecord=null;updateScanReadback();const config=state.current_scan||state.requested_scan;$("scan").textContent=config?`${config.width_px}² · ${(config.field_width_m*1e6).toFixed(2)} μm HFW · native raster`:"Scan —";$("progress").value=state.progress?state.progress.completed_pixels/state.progress.total_pixels:0;
stage.update({xReadback:`X ${(s.x_m*1e3).toFixed(6)} mm`,yReadback:`Y ${(s.y_m*1e3).toFixed(6)} mm`,zReadback:`Z ${(s.z_m*1e6).toFixed(2)} μm`,wdReadback:`WD ${(s.working_distance_m*1e3).toFixed(4)} mm`,motionReadback:state.phase,xyStep:`XY step ${(Number($("hfw").value)/4).toFixed(2)} μm`,zStep:"Z step 0.5 μm",canEditXY:owned,canEditZ:owned,canMove:owned,canStop:owned});
for(const id of ["hfw","live-pixels","beam-current","live-dwell","record-dwell","live","record","focus-minus","focus-plus","focus","focus-slider","stig-x","stig-y","stig-x-slider","stig-y-slider","zoom-in","zoom-out","full-roi","roi-align"])$(id).disabled=!owned;$("record").disabled=!owned||!!pendingRecord;$("stop").disabled=!owned;$("freeze").disabled=!owned||!state.live_source_id;
const acquired=currentImage&&currentImage.parameter_segments.length?currentImage.parameter_segments[currentImage.parameter_segments.length-1]:null;$("optics-readback").textContent=`Applied: ${(state.applied.focus_offset_m*1e6).toFixed(2)} μm · X ${state.applied.stigmator_x.toFixed(2)} / Y ${state.applied.stigmator_y.toFixed(2)}\nAcquired: ${acquired?(acquired.focus_offset_m*1e6).toFixed(2)+" μm · X "+acquired.stigmator_x.toFixed(2)+" / Y "+acquired.stigmator_y.toFixed(2):"—"}${currentImage&&currentImage.parameter_segments.length>1?" (mixed acquisition)":""}${state.requested?"\nAdjustment pending":""}`;
$("beam-readback").textContent=`Selected: ${$("beam-current").value} pA\nApplied: ${state.applied.current_pA} pA\nAcquired: ${acquired?acquired.current_pA+" pA":"—"}${currentImage&&currentImage.parameter_segments.length>1?" (mixed acquisition)":""}`;
const known=new Set(Array.from($("recordings").options).map(o=>o.value));for(const img of state.recorded_images){if(!known.has(img.image_id)){const option=document.createElement("option");option.value=img.image_id;option.textContent=`${img.width_px}² · ${(img.field_width_m*1e6).toFixed(2)} μm · ${img.outcome.toLowerCase()}`;$("recordings").append(option)}}}
function acquiredArguments(){
const m=currentImage;return [imageBytes,m.width_px,m.height_px,m.completed_pixels,m.active_dwell_ns,m.dwell_ns,$("display-units").value];
}
function setWindow(low,high){$("cps-low").value=String(Number(low.toPrecision(10)));$("cps-high").value=String(Number(high.toPrecision(10)))}
function autoWindow(){
if(!currentImage||!imageBytes)return;
const range=VsemIntensityTransfer.autoWindow(...acquiredArguments(),.01,.99);
setWindow(range.low,range.high);lastAutoMs=performance.now();lastAutoOrigin=currentImage.origin_ns;
}
function drawHistogram(){
if(!histogramData)return;
const h=histogramData,c=$("counts-histogram"),g=c.getContext("2d"),width=c.width,height=c.height;
g.fillStyle="#101b23";g.fillRect(0,0,width,height);
const maximum=Math.max(1,...h.counts);g.fillStyle="#7ed9cf";
for(let i=0;i<h.counts.length;i++){const v=Math.log1p(h.counts[i])/Math.log1p(maximum);g.fillRect(i*width/h.counts.length,height*(1-v),Math.ceil(width/h.counts.length),height*v)}
const lo=Number($("cps-low").value),hi=Number($("cps-high").value),span=h.maximum-h.minimum||1;
g.strokeStyle="#ffc784";
for(const value of [lo,hi]){const x=(value-h.minimum)/span*width;g.beginPath();g.moveTo(x,0);g.lineTo(x,height);g.stroke()}
$("histogram-summary").textContent=`${h.sampleCount.toLocaleString()} acquired pixels; ${h.minimum.toPrecision(4)} to ${h.maximum.toPrecision(4)} ${$("display-units").value==="cps"?"counts/s":"counts"}. Latest native raster only; unacquired pixels excluded.`;
$("window-low").value=String(Math.max(0,Math.min(100,(lo-h.minimum)/span*100)));
$("window-high").value=String(Math.max(0,Math.min(100,(hi-h.minimum)/span*100)));
}
function refreshHistogram(force=false){
if(!currentImage||!imageBytes)return;
const key=currentImage.image_id+":"+$("display-units").value;
if(!force&&key===histogramKey)return;
histogramData=VsemIntensityTransfer.histogram(...acquiredArguments(),128);histogramKey=key;
const acquired=currentImage.completed_pixels+(currentImage.active_dwell_ns>0?1:0);
if($("auto-follow").checked&&!parentImage&&acquired&&(lastAutoOrigin!==currentImage.origin_ns||performance.now()-lastAutoMs>=1000||currentImage.outcome!=="ACQUIRING"))autoWindow();
drawHistogram();
}
function scheduleDisplay(){
if(displayFrame!==null)return;
displayFrame=requestAnimationFrame(()=>{displayFrame=null;try{render();if($("error").textContent==="invalid_display_transfer")error("")}catch(e){error(e.message)}});
}
function manualWindow(){
$("auto-follow").checked=false;drawHistogram();scheduleDisplay();
}
function histogramHandle(id){
if(!histogramData||!histogramData.sampleCount)return;
const lowSlider=$("window-low"),highSlider=$("window-high");
if(id==="window-low")lowSlider.value=String(Math.min(Number(lowSlider.value),Number(highSlider.value)-.05));
else highSlider.value=String(Math.max(Number(highSlider.value),Number(lowSlider.value)+.05));
const span=histogramData.maximum-histogramData.minimum||1;
setWindow(histogramData.minimum+Number(lowSlider.value)*span/100,histogramData.minimum+Number(highSlider.value)*span/100);manualWindow();
}
function render(){
if(!currentImage||!imageBytes)return;
const m=currentImage,ref=parentImage||m,composite=!!parentImage&&(m.field_width_m!==ref.field_width_m||m.offset_x_m!==ref.offset_x_m||m.offset_y_m!==ref.offset_y_m);
const cutKey=m.image_id+":"+m.numerical_verified_ordinal+":"+ref.image_id;
if(cutKey!==displayCutKey){
  const configuration=displayBuffer.configure(ref);
  if(configuration.cleared&&parentImage&&parentPixels)displayBuffer.update(parentImage,parentPixels);
  displayBuffer.update(m,imageBytes);displayCutKey=cutKey;
}
refreshHistogram();
const gamma=$("display-gamma")?Number($("display-gamma").value):1;
const brightness=$("display-brightness")?Number($("display-brightness").value):0;
const contrast=$("display-contrast")?Number($("display-contrast").value):1;
const units=$("display-units")?$("display-units").value:"cps";
const pixels=displayBuffer.pixels(Number($("cps-low").value),Number($("cps-high").value),gamma,brightness,contrast,units);
// Resetting canvas dimensions clears it;only resize for an actual viewport-grid
// change. The retained display buffer supplies every unchanged acquisition pixel.
if(canvas.width!==ref.width_px||canvas.height!==ref.height_px){canvas.width=ref.width_px;canvas.height=ref.height_px}
ctx.putImageData(new ImageData(pixels,ref.width_px,ref.height_px),0,0);
if(composite){
  if(roiCutKey!==cutKey){roiDisplayBuffer.configure(m);roiDisplayBuffer.update(m,imageBytes);roiCutKey=cutKey}
  const detailPixels=roiDisplayBuffer.pixels(Number($("cps-low").value),Number($("cps-high").value),gamma,brightness,contrast,units);
  const native=roiDisplayBuffer.snapshot();
  for(let i=0;i<native.valid.length;i++)if(!native.valid[i])detailPixels[i*4+3]=0;
  if(roiCanvas.width!==m.width_px||roiCanvas.height!==m.height_px){roiCanvas.width=m.width_px;roiCanvas.height=m.height_px}
  roiContext.putImageData(new ImageData(detailPixels,m.width_px,m.height_px),0,0);
  const surveyHeight=ref.height_px*ref.pixel_pitch_m,detailHeight=m.height_px*m.pixel_pitch_m;
  roiCanvas.style.left=(50+100*(m.offset_x_m-ref.offset_x_m-m.field_width_m/2)/ref.field_width_m)+"%";
  roiCanvas.style.top=(50-100*(m.offset_y_m-ref.offset_y_m+detailHeight/2)/surveyHeight)+"%";
  roiCanvas.style.width=100*m.field_width_m/ref.field_width_m+"%";roiCanvas.style.height=100*detailHeight/surveyHeight+"%";
  roiCanvas.style.display="block";roiCanvas.dataset.nativePitch=String(m.pixel_pitch_m);
}else{roiCanvas.style.display="none";roiDisplayBuffer.reset();roiCutKey=null}

$("empty").style.display="none";$("image-caption").dataset.imageId=m.image_id;
$("image-caption").dataset.viewportHfw=String(ref.field_width_m);
$("image-caption").textContent=`SE \u00b7 ${(ref.field_width_m*1e6).toFixed(2)} \u00b5m survey HFW\n${Math.round(ref.magnification).toLocaleString()}x \u00b7 display ${ref.width_px} x ${ref.height_px}${composite?`\nROI ${(m.field_width_m*1e6).toFixed(2)} \u00b5m \u00b7 native ${m.width_px} x ${m.height_px}`:""}\n${m.outcome.toLowerCase()} \u00b7 source ${m.source_id}`;
$("scale").style.width="20%";$("scale").textContent=(ref.field_width_m*1e6/5).toFixed(2)+" \u00b5m";
$("capture-note").textContent=`Acquired XYZ ${(m.stage.x_m*1e6).toFixed(2)}, ${(m.stage.y_m*1e6).toFixed(2)}, ${(m.stage.z_m*1e6).toFixed(2)} \u00b5m \u00b7 ${(m.incident_pA_ns/1e12).toFixed(3)} nC \u00b7 ${(m.cut_elapsed_ns/1e9).toFixed(3)} s capture cut \u00b7 pixels not yet overwritten retain earlier acquisition${composite?"; outside ROI is an older survey":""}${selectedImage==="reopened-file"?" \u00b7 reopened file;provenance unverified":""}`;
}
async function loadImage(id){const metadata=await request("/image/"+id);const response=await fetch("/image/"+id+"/SE");if(!response.ok)throw Error("native_image_unavailable");imageBytes=await response.arrayBuffer();currentImage=metadata;
if(desiredViewport&&metadata.origin_ns>=desiredViewport.minOrigin&&["width_px","height_px","field_width_m","offset_x_m","offset_y_m","dwell_ns"].every(key=>metadata[key]===desiredViewport[key])){parentImage=null;parentPixels=null;desiredViewport=null}
render();updateState()}
async function refresh(){if(refreshing)return;refreshing=true;try{await sync();if(pendingRecord){const op=await request("/operation/"+pendingRecord.operationId);if(op.status==="REJECTED"||op.status==="UNKNOWN"||(op.status==="CANCELLED"&&op.reason==="STOPPED_BEFORE_ADMISSION")){pendingRecord=null;error(op.reason||op.status);updateState()}}const id=selectedImage==="reopened-file"?null:selectedImage||(state.latest_image&&state.latest_image.image_id);if(id&&(!currentImage||currentImage.image_id!==id))await loadImage(id);if($("error").textContent==="Failed to fetch")error("")}catch(e){error(e.message)}finally{refreshing=false}}
function action(id,callback){$(id).addEventListener("click",()=>callback().catch(e=>error(e.message)))}
action("control",async()=>{await waitOperation(await request("/lease",{}));await sync();error("")});action("stop",stop);action("live",live);action("record",record);action("freeze",async()=>{await command("freeze",{source_id:state.live_source_id});running=false});
action("focus-minus",async()=>{$("focus").value=Math.max(-25,Number($("focus").value)-Number($("focus-step").value));$("focus-slider").value=$("focus").value;await applyOptics()});action("focus-plus",async()=>{$("focus").value=Math.min(25,Number($("focus").value)+Number($("focus-step").value));$("focus-slider").value=$("focus").value;await applyOptics()});
$("beam-current").addEventListener("change",scheduleOptics);
$("live-dwell").addEventListener("change",()=>{if(state&&state.live_source_id)command("configure_live",scanParameters()).catch(e=>error(e.message));if(state)updateState()});
$("record-dwell").addEventListener("change",()=>{if(state)updateState()});
for(const id of ["focus","stig-x","stig-y"])$(id).addEventListener("input",()=>{$(id+"-slider").value=$(id).value;scheduleOptics()});for(const id of ["focus-slider","stig-x-slider","stig-y-slider"])$(id).addEventListener("input",()=>{$(id.replace("-slider","")).value=$(id).value;scheduleOptics()});
async function changeField(value){$("hfw").value=Math.min(5000,Math.max(1,value));roi={field_width_m:Number($("hfw").value)*1e-6,offset_x_m:0,offset_y_m:0};$("roi").style.display="none";const parameters=scanParameters();desiredViewport={...parameters,minOrigin:state.observed_at_ns||0};if(state.live_source_id)await command("configure_live",parameters);else if(state.phase!=="STOPPED"||running)await live()}
action("zoom-in",()=>changeField(Number($("hfw").value)/2));action("zoom-out",()=>changeField(Number($("hfw").value)*2));$("hfw").addEventListener("change",()=>changeField(Number($("hfw").value)).catch(e=>error(e.message)));action("full-roi",()=>changeField(Number($("hfw").value)));
function retainParent(){
  desiredViewport=null;selectedImage="";$("recordings").value="";
  if(!parentImage){
    parentImage=currentImage;
    // Pin the acquired background before asynchronous Stop/start/refresh can
    // select a different raster. Metadata alone cannot restore a cleared grid.
    parentPixels=imageBytes.slice(0);
    displayBuffer.reset();displayBuffer.configure(parentImage);
    displayBuffer.update(parentImage,parentPixels);displayCutKey=null;
  }
}
action("roi-align",async()=>{if(!currentImage)throw Error("Acquire a survey image first");retainParent();roi={field_width_m:Math.max(1e-7,parentImage.field_width_m/2),offset_x_m:parentImage.offset_x_m,offset_y_m:parentImage.offset_y_m};const width=roi.field_width_m/parentImage.field_width_m,box=$("roi");box.style.display="block";box.style.left=box.style.top=(1-width)*50+"%";box.style.width=box.style.height=width*100+"%";$("live-pixels").value="64";if(state.live_source_id)await command("configure_live",scanParameters());else await live()});
let drag=null;canvas.addEventListener("pointerdown",event=>{if(!state||!state.control_owned||!currentImage)return;const rect=canvas.getBoundingClientRect();drag={x:(event.clientX-rect.left)/rect.width,y:(event.clientY-rect.top)/rect.height};canvas.setPointerCapture(event.pointerId)});canvas.addEventListener("pointerup",event=>{if(!drag)return;const rect=canvas.getBoundingClientRect(),x=(event.clientX-rect.left)/rect.width,y=(event.clientY-rect.top)/rect.height;let width=Math.max(Math.abs(x-drag.x),Math.abs(y-drag.y));const base=parentImage||currentImage;if(width<.03){drag=null;return}const field=Math.max(1e-7,Math.min(base.field_width_m,width*base.field_width_m));width=field/base.field_width_m;const cx=Math.max(width/2,Math.min(1-width/2,(x+drag.x)/2)),cy=Math.max(width/2,Math.min(1-width/2,(y+drag.y)/2));drag=null;retainParent();roi={field_width_m:field,offset_x_m:base.offset_x_m+(cx-.5)*base.field_width_m,offset_y_m:base.offset_y_m+(.5-cy)*base.field_width_m};const box=$("roi");box.style.display="block";box.style.left=(cx-width/2)*100+"%";box.style.top=(cy-width/2)*100+"%";box.style.width=box.style.height=width*100+"%";$("live-pixels").value="64";(state.live_source_id?command("configure_live",scanParameters()):live()).catch(e=>error(e.message))});
$("live-pixels").addEventListener("change",()=>{if(!state)return;if(state.live_source_id)command("configure_live",scanParameters()).catch(e=>error(e.message));else if(state.phase!=="STOPPED")live().catch(e=>error(e.message))});
for(const id of ["cps-low","cps-high"])$(id).addEventListener("input",manualWindow);
for(const id of ["display-gamma","display-brightness","display-contrast"])$(id).addEventListener("input",scheduleDisplay);
for(const id of ["window-low","window-high"])$(id).addEventListener("input",()=>histogramHandle(id));
$("display-units").addEventListener("change",()=>{try{histogramKey=null;refreshHistogram(true);autoWindow();drawHistogram();scheduleDisplay()}catch(e){error(e.message)}});
$("auto-window").addEventListener("click",()=>{try{autoWindow();drawHistogram();scheduleDisplay()}catch(e){error(e.message)}});
$("auto-follow").addEventListener("change",()=>{if($("auto-follow").checked){autoWindow();drawHistogram();scheduleDisplay()}});
$("recordings").addEventListener("change",()=>{selectedImage=$("recordings").value;parentImage=null;parentPixels=null;desiredViewport=null;displayBuffer.reset();displayCutKey=null;histogramKey=null;const id=selectedImage||(state.latest_image&&state.latest_image.image_id);if(id)loadImage(id).catch(e=>error(e.message))});
$("download").addEventListener("click",()=>{if(!imageBytes||!currentImage)return;const bytes=new Uint8Array(imageBytes);let binary="";for(let i=0;i<bytes.length;i+=32768)binary+=String.fromCharCode(...bytes.subarray(i,i+32768));const record={protocol:"vsem.core-acquired-file.v1",image:currentImage,SE_uint32_base64:btoa(binary)};const blob=new Blob([JSON.stringify(record)],{type:"application/json"}),url=URL.createObjectURL(blob),link=document.createElement("a");link.href=url;link.download=`vsem-${currentImage.width_px}x${currentImage.height_px}-${currentImage.image_id}.vsem.json`;link.click();URL.revokeObjectURL(url)});
$("reopen").addEventListener("click",()=>$("acquired-file").click());
function validateAcquiredMetadata(m){
const keys=["protocol","image_id","source_id","mode","outcome","terminal_reason","origin_ns","cut_elapsed_ns","numerical_verified_ordinal","causal_verified_ordinal","width_px","height_px","completed_pixels","active_dwell_ns","dwell_ns","field_width_m","pixel_pitch_m","magnification","magnification_reference_width_m","stage","offset_x_m","offset_y_m","incident_pA_ns","parameter_segments","blank_holds","raw_format","calibration_status","detector"];
const exact=(value,allowed)=>value&&typeof value==="object"&&!Array.isArray(value)&&Object.keys(value).sort().join(",")===allowed.slice().sort().join(",");
const finite=value=>typeof value==="number"&&Number.isFinite(value);
if(!exact(m,keys)||!["vsem.core-native-image.v1","vsem.core-native-image.v2"].includes(m.protocol)||m.calibration_status!=="generic_uncalibrated"||m.detector!=="SE"||m.raw_format!=="uint32_little_endian"||!exact(m.stage,["x_m","y_m","z_m","working_distance_m"]))throw Error("invalid_captured_metadata");
if(!["LIVE","SINGLE"].includes(m.mode)||!["ACQUIRING","COMPLETED","CANCELLED"].includes(m.outcome)||typeof m.image_id!=="string"||typeof m.source_id!=="string")throw Error("invalid_capture_identity");
for(const key of ["origin_ns","cut_elapsed_ns","numerical_verified_ordinal","causal_verified_ordinal","incident_pA_ns"]){if(!Number.isSafeInteger(m[key])||m[key]<0)throw Error("invalid_capture_integer")}
for(const key of ["field_width_m","pixel_pitch_m","magnification","magnification_reference_width_m","offset_x_m","offset_y_m"]){if(!finite(m[key]))throw Error("invalid_capture_geometry")}
for(const value of Object.values(m.stage)){if(!finite(value))throw Error("invalid_captured_stage")}
if(m.field_width_m<=0||m.pixel_pitch_m!==m.field_width_m/m.width_px||m.magnification_reference_width_m!==.1||Math.abs(m.magnification-.1/m.field_width_m)>1e-8)throw Error("invalid_capture_scale");
if(!Array.isArray(m.parameter_segments)||!m.parameter_segments.length||m.parameter_segments.length>65536||!Array.isArray(m.blank_holds)||m.blank_holds.length>65536)throw Error("invalid_capture_segments");
const segmentKeys=["start_elapsed_ns","end_elapsed_ns","current_pA","focus_offset_m","stigmator_x","stigmator_y"];
for(const s of m.parameter_segments){if(!exact(s,m.protocol==="vsem.core-native-image.v2"?[...segmentKeys,"stage"]:segmentKeys)||!segmentKeys.every(key=>finite(s[key]))||!Number.isSafeInteger(s.start_elapsed_ns)||!Number.isSafeInteger(s.end_elapsed_ns)||s.start_elapsed_ns<0||s.end_elapsed_ns<s.start_elapsed_ns||s.end_elapsed_ns>m.cut_elapsed_ns)throw Error("invalid_capture_segment");
if(m.protocol==="vsem.core-native-image.v2"&&(!exact(s.stage,["x_m","y_m","z_m","working_distance_m"])||!Object.values(s.stage).every(finite)||Math.abs(s.stage.working_distance_m-(.010-s.stage.z_m))>1e-12))throw Error("invalid_captured_segment_stage")}

for(const h of m.blank_holds){if(!exact(h,["start_elapsed_ns","end_elapsed_ns"])||!Number.isSafeInteger(h.start_elapsed_ns)||!Number.isSafeInteger(h.end_elapsed_ns)||h.start_elapsed_ns<0||h.end_elapsed_ns<h.start_elapsed_ns||h.end_elapsed_ns>m.cut_elapsed_ns)throw Error("invalid_capture_hold")}
}
$("acquired-file").addEventListener("change",async()=>{try{const file=$("acquired-file").files[0];if(!file)return;if(file.size>100000000)throw Error("acquisition_file_too_large");const record=JSON.parse(await file.text());if(!record||Object.keys(record).sort().join(',')!=="SE_uint32_base64,image,protocol"||record.protocol!=="vsem.core-acquired-file.v1")throw Error("unsupported_acquisition_file");const m=record.image;validateAcquiredMetadata(m);if(typeof record.SE_uint32_base64!=="string")throw Error("invalid_native_bytes");const binary=atob(record.SE_uint32_base64),bytes=new Uint8Array(binary.length);for(let i=0;i<binary.length;i++)bytes[i]=binary.charCodeAt(i);VsemIntensityTransfer.histogram(bytes.buffer,m.width_px,m.height_px,m.completed_pixels,m.active_dwell_ns,m.dwell_ns,"counts",2);selectedImage="reopened-file";currentImage=m;imageBytes=bytes.buffer;parentImage=null;parentPixels=null;displayBuffer.reset();displayCutKey=null;histogramKey=null;render();error("")}catch(e){error(e.message)}});
request("/session").then(session=>{csrf=session.csrf;refresh();setInterval(refresh,150);setInterval(()=>{if(state&&state.control_owned)request("/lease",{}).catch(e=>error(e.message))},10000)}).catch(e=>error(e.message));
})();
