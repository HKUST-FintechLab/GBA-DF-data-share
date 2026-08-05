const I18N = window.GBA_DF_I18N;
let LANG="en", MODS=[], sel={modality:null, mInfo:null, folder:null, scan:null, sch:null, invitation:null};
let videoOutput={path:"",temporary:true};
let conn={state:"off", host:""};      // off | on | run | done
const HOLISTIC_VERSION="0.5.1675471629";
const HOLISTIC_CDN=`https://cdn.jsdelivr.net/npm/@mediapipe/holistic@${HOLISTIC_VERSION}`;
const HOLISTIC_LOCAL="vendor/mediapipe";
// Populated by resolveAssetSource(): a mirrored copy (fetch_offline_assets.py) is preferred over
// the public CDN, so a locked-down hospital network needs no third-party access at run time.
const assets={base:HOLISTIC_CDN, offline:false, manifest:null};
async function resolveAssetSource(){
  if(assets.manifest!==null) return assets;
  try{
    const r=await fetch(`${HOLISTIC_LOCAL}/manifest.json`,{cache:"no-store"});
    if(r.ok){
      const m=await r.json();
      if(m?.format==="gba-df-offline-assets" && m.package_version===HOLISTIC_VERSION && m.files){
        assets.base=HOLISTIC_LOCAL; assets.offline=true; assets.manifest=m.files;
        return assets;
      }
    }
  }catch(_e){ /* no local mirror — fall back to the CDN below */ }
  assets.manifest={}; return assets;
}
async function sha256Hex(buffer){
  if(!globalThis.crypto?.subtle) return null;         // not a secure context: skip, don't block
  const digest=await crypto.subtle.digest("SHA-256",buffer);
  return Array.from(new Uint8Array(digest)).map(b=>b.toString(16).padStart(2,"0")).join("");
}
const videoImport={running:false,cancelled:false,holistic:null,ready:false,lastResults:null,activeVideo:null,
  pendingFiles:null,pendingDest:null};
const api = () => window.pywebview.api;
const t = k => (I18N[LANG][k] ?? k);
const $ = s => document.querySelector(s);
const isChinese = () => LANG === "zh" || LANG === "zh-Hant";
const isTraditional = () => LANG === "zh-Hant";
const HANT_MODALITIES = {
  eyegaze:{name:"眼動資料", task:"社交注意力篩查 (ASD/TD)", hint:"每段錄製一個 CSV（欄位含 x、y[, pupil]），置於 asd/ 與 td/ 子資料夾"},
  action:{name:"動作／姿態資料", task:"行為動作篩查 (ASD/TD)", hint:"選擇現有 body:(T,33,4) NPZ，或在桌面客戶端本地轉換原始影片"},
  action_cdp:{name:"動作／姿態資料（CDP 實驗）", task:"CDP 聯邦適配實驗 (ASD/TD)", hint:"使用固定 CDP 40+64 特徵適配器；選擇 body:(T,33,4) NPZ，或在本機轉換原始影片"},
  neuro:{name:"EEG／fMRI 神經影像", task:"神經影像篩查 (ASD/TD)", hint:"每次掃描一個 .npz（鍵 'ts'，通道×時間）或 CSV，置於 asd/ 與 td/ 子資料夾"}
};

function applyLang(){
  document.querySelectorAll("[data-i]").forEach(el=>{ const k=el.getAttribute("data-i"); if(I18N[LANG][k]!=null) el.textContent=I18N[LANG][k]; });
  document.querySelectorAll("[data-i-placeholder]").forEach(el=>{ const k=el.getAttribute("data-i-placeholder"); if(I18N[LANG][k]!=null) el.placeholder=I18N[LANG][k]; });
  $("#zhHans").classList.toggle("on",LANG==="zh"); $("#zhHant").classList.toggle("on",LANG==="zh-Hant"); $("#en").classList.toggle("on",LANG==="en");
  document.documentElement.lang = LANG;
  renderMods(); renderSteps(); updateS2Hint(); updateActionControls(); renderVideoOutput(); renderThemeSettings(); renderStatus(); renderPrivacyCopy(); updateConsoleChrome();
}
$("#zhHans").onclick=()=>{LANG="zh";applyLang();};
$("#zhHant").onclick=()=>{LANG="zh-Hant";applyLang();};
$("#en").onclick=()=>{LANG="en";applyLang();};

function renderStatus(){
  const map={off:"st_off",on:"st_on",run:"st_run",done:"st_done"};
  const dot=$("#stDot"); dot.className="stdot"+(conn.state==="on"||conn.state==="done"?" on":(conn.state==="run"?" busy":""));
  $("#stConn").textContent = t(map[conn.state]) + (conn.host?` · ${conn.host}`:"");
  updateConsoleChrome();
}
function setConn(state, host){ conn.state=state; if(host!=null) conn.host=host; renderStatus(); }
function renderTraffic(s){
  const total=s?.application_bytes_sent||0, masked=s?.masked_payload_bytes_sent||0;
  const metadata=s?.protocol_metadata_bytes_sent||0;
  const secure=sel.sch?.secure_aggregation!==false;
  $("#rsTx").textContent=humanBytes(total);
  $("#rsTxDetail").textContent=`${t(secure?"tx_masked":"tx_counts")} ${humanBytes(masked)} · ${t("tx_metadata")} ${humanBytes(metadata)}`;
  $("#stShared").textContent=total?t("st_shared_bytes").replace("{bytes}",humanBytes(total)):t(secure?"st_shared":"st_shared_solo");
}
function renderPrivacyCopy(){
  const secure=sel.sch?.secure_aggregation!==false;
  const banner=document.querySelector('[data-i="s4_banner"]'),note=document.querySelector('[data-i="s4_note"]');
  if(banner) banner.textContent=t(secure?"s4_banner":"s4_banner_solo");
  if(note) note.textContent=t(secure?"s4_note":"s4_note_solo");
  renderTraffic(null);
}

const STEP_LABELS={en:["Data type","Folder","Connect","Train"],zh:["数据类型","文件夹","连接","训练"],"zh-Hant":["資料類型","資料夾","連線","訓練"]};
let curStep=1;
const CONSOLE_SCENE_KEYS=[null,"s1","s2","s3","s4"];
function consoleModalityName(){
  if(!sel.mInfo)return "";
  const traditional=HANT_MODALITIES[sel.mInfo.key];
  return isTraditional()?(traditional?.name||sel.mInfo.en):(isChinese()?sel.mInfo.zh:sel.mInfo.en);
}
function updateConsoleChrome(){
  if(!$("#consoleSceneIndex"))return;
  const key=CONSOLE_SCENE_KEYS[curStep];
  const label=STEP_LABELS[LANG][curStep-1].toUpperCase();
  const summary=curStep===1?consoleModalityName():(curStep===2&&sel.scan?`${sel.scan.n_samples} · ${sel.scan.n_features}F`:"");
  $("#consoleSceneIndex").textContent=`0${curStep} / ${label}${summary?`  ·  ${summary}`:""}`;
  $("#consoleSceneTitle").textContent=t(`${key}_h`);
  $("#consoleSceneSub").textContent=curStep===2
    ?(sel.mInfo?$("#s2hint").textContent:t("s2_note"))
    :t(curStep===4?(sel.sch?.secure_aggregation===false?"s4_banner_solo":"s4_banner"):`${key}_hint`);

  const back=$("#consoleBack"),next=$("#consoleNext"),start=$("#consoleStart");
  back.disabled=curStep===1||curStep===4;
  back.textContent=`◁ ${t("back").toLowerCase()}`;
  next.classList.toggle("hidden",curStep>=3);
  next.disabled=curStep===1||!sel.scan||videoImport.running;
  next.textContent=`${t("next").toLowerCase()} ▷`;
  start.classList.toggle("hidden",curStep!==3);
  start.disabled=$("#s3next").disabled;
  start.textContent=`${t("s3_start").toLowerCase()} ▷`;
  $("#consoleStop").classList.toggle("hidden",curStep!==4||$("#stop").classList.contains("hidden"));
  $("#consoleStop").disabled=$("#stop").disabled;
  $("#consoleRestart").classList.toggle("hidden",curStep!==4||$("#restart").classList.contains("hidden"));

  const dots=$("#consoleDots");dots.innerHTML="";
  STEP_LABELS[LANG].forEach((_text,index)=>{
    const dot=document.createElement("i"),step=index+1;
    dot.className=(step===curStep?"on":"")+(step<curStep?" done":"");
    dots.appendChild(dot);
  });
}
function renderSteps(){
  const s=$("#steps"); s.innerHTML="";
  STEP_LABELS[LANG].forEach((lb,i)=>{
    const n=i+1, d=document.createElement("div");
    d.className="stepdot"+(n===curStep?" active":"")+(n<curStep?" done":"");
    d.innerHTML=`<span class="n">${n<curStep?"✓":n}</span><span>${lb}</span>`;
    s.appendChild(d);
  });
}
function goStep(n){
  curStep=n;
  document.querySelectorAll("[data-step]").forEach(el=>el.classList.toggle("hidden",+el.getAttribute("data-step")!==n));
  renderSteps();
  updateConsoleChrome();
  window.GBADFTheme?.step(n);
}
document.querySelectorAll("[data-back]").forEach(b=>b.onclick=()=>goStep(+b.getAttribute("data-back")));
$("#consoleBack").onclick=()=>{if(curStep>1&&curStep<4)goStep(curStep-1);};
$("#consoleNext").onclick=()=>{if(curStep===2&&!$("#s2next").disabled)$("#s2next").click();};
$("#consoleStart").onclick=()=>{if(!$("#s3next").disabled)$("#s3next").click();};
$("#consoleStop").onclick=()=>$("#stop").click();
$("#consoleRestart").onclick=()=>$("#restart").click();

const ICONS={eyegaze:"👁️",action:"🏃",action_cdp:"🧩",neuro:"🧠"};
function renderMods(){
  const box=$("#mods"); box.innerHTML="";
  MODS.forEach(m=>{
    const localized = isTraditional()?HANT_MODALITIES[m.key]:null;
    const nm = localized?.name || (isChinese()?m.zh:m.en);
    const tk = localized?.task || (isChinese()?m.task_zh:m.task_en);
    const d=document.createElement("div");
    d.className="mod"+(sel.modality===m.key?" sel":"");
    d.innerHTML=`<div class="ic">${ICONS[m.key]||"📊"}</div><div class="nm">${nm}</div>
      <div class="tk">${tk}</div><div class="dim">${m.n_features} ${t("feats")}</div>`;
    d.onclick=()=>{ if(videoImport.running) return; sel.modality=m.key; sel.mInfo=m; sel.folder=null; sel.scan=null;
      $("#foldbox").classList.add("hidden"); $("#s2msg").innerHTML=""; $("#s2next").disabled=true;
      renderMods(); updateS2Hint(); updateActionControls(); goStep(2); };
    box.appendChild(d);
  });
  window.GBADFTheme?.refresh();
  updateConsoleChrome();
}
function updateS2Hint(){
  if(!sel.mInfo)return;
  $("#s2hint").textContent=isTraditional()?(HANT_MODALITIES[sel.mInfo.key]?.hint||sel.mInfo.file_hint):
    (isChinese()?sel.mInfo.file_hint.split("·")[0]:sel.mInfo.file_hint.split("·")[1]||sel.mInfo.file_hint);
  updateConsoleChrome();
}
function updateActionControls(){
  const action=sel.modality==="action"||sel.modality==="action_cdp";
  const cdp=sel.modality==="action_cdp";
  $("#pickvideo").classList.toggle("hidden",!action);
  $("#videoImport").classList.toggle("hidden",!action);
  $("#pick").textContent=action?t("pick_npz"):t("pick");
  if(cdp) $("#videoFps").value="4";
  $("#videoFps").disabled=cdp||videoImport.running;
}
function renderVideoOutput(){
  if(!$("#videoOutputPath"))return;
  $("#videoOutputPath").textContent=videoOutput.path||"—";
  $("#videoOutputBadge").textContent=t(videoOutput.temporary?"video_output_temp":"video_output_permanent");
  $("#resetVideoOutput").classList.toggle("hidden",videoOutput.temporary);
}
async function refreshVideoOutput(){
  try{
    const result=await api().video_output();
    if(result?.ok){videoOutput=result;renderVideoOutput();}
  }catch(_e){}
}

const UI_THEMES=new Set(["classic","console"]);
function currentTheme(){
  const value=document.documentElement.dataset.theme;
  return UI_THEMES.has(value)?value:"classic";
}
function renderThemeSettings(){
  const active=currentTheme();
  document.querySelectorAll("[data-theme-choice]").forEach(button=>{
    const on=button.dataset.themeChoice===active;
    button.classList.toggle("on",on);
    button.setAttribute("aria-checked",String(on));
  });
}
function applyTheme(theme,{persist=true}={}){
  const selected=UI_THEMES.has(theme)?theme:"classic";
  document.documentElement.dataset.theme=selected;
  if(persist){
    try{localStorage.setItem("gba-df-ui-theme",selected);}catch(_error){}
  }
  renderThemeSettings();
  window.GBADFTheme?.change(selected);
}
function openSettings(){
  renderThemeSettings(); refreshVideoOutput();
  $("#settingsModal").classList.remove("hidden");
  setTimeout(()=>$("#closeSettings").focus(),0);
}
function closeSettings(){$("#settingsModal").classList.add("hidden");}
$("#openSettings").onclick=openSettings;
$("#consoleSettings").onclick=openSettings;
$("#closeSettings").onclick=closeSettings;
$("#settingsModal").onclick=event=>{if(event.target===$("#settingsModal"))closeSettings();};
document.querySelectorAll("[data-theme-choice]").forEach(button=>{
  button.onclick=()=>applyTheme(button.dataset.themeChoice);
});

const CONNECTION_CONFIG_FORMAT="gba-df-client-config";
const CONNECTION_CONFIG_VERSIONS=[1,2];
const INVITATION_FORMAT="gba-df-invitation";
function openConfigImport(){
  $("#configMsg").innerHTML="";
  $("#configModal").classList.remove("hidden");
  setTimeout(()=>$("#configJson").focus(),0);
}
function closeConfigImport(){ $("#configModal").classList.add("hidden"); }
function cleanCoordinatorUrl(value){
  if(typeof value!=="string") return null;
  try{
    const url=new URL(value.trim());
    if(!["http:","https:"].includes(url.protocol)||!url.hostname||url.username||url.password) return null;
    if(url.pathname!=="/"||url.search||url.hash) return null;
    return url.origin;
  }catch(_e){ return null; }
}
function importConnectionConfig(){
  let config;
  try{ config=JSON.parse($("#configJson").value); }
  catch(_e){ msg("#configMsg","bad",t("config_invalid_json")); return; }
  if(!config||Array.isArray(config)||typeof config!=="object") { msg("#configMsg","bad",t("config_invalid")); return; }
  if(config.format!=null && config.format!==CONNECTION_CONFIG_FORMAT){ msg("#configMsg","bad",t("config_unknown_format")); return; }
  if(config.version!=null && !CONNECTION_CONFIG_VERSIONS.includes(config.version)){ msg("#configMsg","bad",t("config_unknown_format")); return; }
  const coord=cleanCoordinatorUrl(config.coordinator_url??config.coord);
  const password=config.password??config.key;
  const nodeId=config.node_id;
  const name=config.display_name??config.name;
  const rounds=config.rounds;
  // The invitation is forwarded to the coordinator untouched — it alone verifies the signature.
  const invitation=config.invitation;
  if(!coord || (password!=null&&typeof password!=="string") || (nodeId!=null&&typeof nodeId!=="string") ||
      (name!=null&&typeof name!=="string") || (rounds!=null&&(!Number.isInteger(rounds)||rounds<1||rounds>20)) ||
      (typeof password==="string"&&password.length>4096) || (typeof nodeId==="string"&&nodeId.length>128) ||
      (typeof name==="string"&&name.length>160)) { msg("#configMsg","bad",t("config_invalid")); return; }
  if(invitation!=null && (typeof invitation!=="object"||Array.isArray(invitation)||invitation.format!==INVITATION_FORMAT)){
    msg("#configMsg","bad",t("config_invalid_invitation")); return; }
  sel.invitation=invitation??null;
  $("#coord").value=coord;
  if(typeof password==="string") $("#passwd").value=password;
  if(typeof nodeId==="string") $("#nodeid").value=nodeId;
  if(typeof name==="string") $("#nodename").value=name;
  if(rounds!=null) $("#rounds").value=String(rounds);
  sel.sch=null; $("#s3next").disabled=true; setConn("off",""); closeConfigImport();
  msg("#s3msg","warn",t(sel.invitation?"config_imported_invited":"config_imported"));
}

$("#importConfig").onclick=openConfigImport;
$("#cancelConfig").onclick=closeConfigImport;
$("#applyConfig").onclick=importConnectionConfig;
$("#configModal").onclick=event=>{ if(event.target===$("#configModal")) closeConfigImport(); };
document.addEventListener("keydown",event=>{
  if(event.key!=="Escape")return;
  if(!$("#settingsModal").classList.contains("hidden"))closeSettings();
  else if(!$("#configModal").classList.contains("hidden"))closeConfigImport();
});

function msg(sel_, kind, html){ $(sel_).innerHTML=`<div class="msg ${kind}">${html}</div>`; }

const POSE_CONNECTIONS=[
  [0,1],[1,2],[2,3],[3,7],[0,4],[4,5],[5,6],[6,8],[9,10],
  [11,12],[11,13],[13,15],[15,17],[15,19],[15,21],[17,19],
  [12,14],[14,16],[16,18],[16,20],[16,22],[18,20],
  [11,23],[12,24],[23,24],[23,25],[25,27],[27,29],[29,31],[27,31],
  [24,26],[26,28],[28,30],[30,32],[28,32]
];

function appendExtractLog(text, bad=false){
  const line=document.createElement("div");
  line.textContent=text; if(bad) line.style.color="var(--bad)";
  $("#extractLog").appendChild(line); $("#extractLog").scrollTop=$("#extractLog").scrollHeight;
}
function setExtractProgress(fraction, status, count){
  $("#extractFill").style.width=(Math.max(0,Math.min(1,fraction))*100).toFixed(1)+"%";
  $("#extractStatus").textContent=status||"—"; $("#extractCount").textContent=count||"";
}
function setVideoBusy(busy){
  videoImport.running=busy;
  ["#pick","#pickvideo","#gendemo","#videoLabel","#videoFps","#changeVideoOutput","#resetVideoOutput"]
    .forEach(s=>$(s).disabled=busy);
  if(sel.modality==="action_cdp") $("#videoFps").disabled=true;
  $("#cancelVideo").classList.toggle("hidden",!busy);
  $("#s2next").disabled=busy||!sel.scan;
  updateConsoleChrome();
}
class MediaPipeLoadError extends Error{constructor(message,cause=null){super(message);this.name="MediaPipeLoadError";this.cause=cause;this.isMediaPipeLoad=true;}}
function humanBytes(n){return n<1024?`${n} B`:n<1048576?`${(n/1024).toFixed(0)} KB`:`${(n/1048576).toFixed(1)} MB`;}
function showCdnLoad({failed=false,title=null,detail=null,progress=null,indeterminate=false,retry=false}={}){
  const box=$("#cdnLoad");box.classList.remove("hidden");box.classList.toggle("failed",failed);
  $("#cdnTitle").textContent=title||t(failed?"cdn_failed":"cdn_title");$("#cdnDetail").textContent=detail||t("cdn_connecting");
  $("#cdnProgress").classList.toggle("hidden",failed);$("#cdnProgress").classList.toggle("indeterminate",indeterminate);
  $("#cdnFill").style.width=progress==null?"0":`${Math.max(0,Math.min(1,progress))*100}%`;
  $("#retryCdn").classList.toggle("hidden",!retry);
}
function hideCdnLoad(){$("#cdnLoad").classList.add("hidden");}
function cdnFailureDetail(error){
  if(typeof navigator!=="undefined"&&navigator.onLine===false)return t("cdn_offline");
  if(error?.name==="AbortError"||/timeout/i.test(error?.message||""))return t("cdn_timeout");
  const raw=String(error?.message||error||"").replace(/^MediaPipeLoadError:\s*/,"");
  return raw?`${raw}. ${t("cdn_help")}`:t("cdn_help");
}
async function loadScript(src,onProgress,expectedSha){
  const old=document.querySelector(`script[data-src="${src}"]`);
  if(old?.dataset.loaded==="1")return;
  if(old)old.remove();
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),30000);
  let response;
  try{response=await fetch(src,{mode:"cors",cache:"default",signal:controller.signal});}
  catch(error){clearTimeout(timer);throw new MediaPipeLoadError(error.name==="AbortError"?"CDN download timeout":"CDN connection failed",error);}
  clearTimeout(timer);
  if(!response.ok)throw new MediaPipeLoadError(`CDN returned HTTP ${response.status}`);
  const total=Number(response.headers.get("content-length"))||0;let received=0,blob;
  if(response.body?.getReader){
    const reader=response.body.getReader(),chunks=[];
    while(true){const {done,value}=await reader.read();if(done)break;chunks.push(value);received+=value.byteLength;onProgress?.(total?Math.min(1,received/total):null,received,total);}
    blob=new Blob(chunks,{type:"application/javascript"});
  }else{blob=await response.blob();received=blob.size;onProgress?.(1,received,received);}
  if(expectedSha){
    // Check the bytes BEFORE they become executable script.
    const actual=await sha256Hex(await blob.arrayBuffer());
    if(actual && actual!==expectedSha) throw new MediaPipeLoadError("MediaPipe loader failed its pinned hash check");
  }
  const objectUrl=URL.createObjectURL(blob);
  await new Promise((resolve,reject)=>{
    const s=document.createElement("script");s.src=objectUrl;s.async=true;s.dataset.src=src;
    s.onload=()=>{s.dataset.loaded="1";URL.revokeObjectURL(objectUrl);resolve();};
    s.onerror=()=>{s.remove();URL.revokeObjectURL(objectUrl);reject(new MediaPipeLoadError("MediaPipe JavaScript could not start"));};
    document.head.appendChild(s);
  });
}
async function ensureHolistic(){
  if(videoImport.holistic) return videoImport.holistic;
  const src=await resolveAssetSource();
  showCdnLoad({detail:t(src.offline?"assets_local":"cdn_connecting"),indeterminate:true});
  setExtractProgress(0,t("video_loading"),"");
  try{
    await loadScript(`${src.base}/holistic.js`,(fraction,received,total)=>{
      const amount=total?`${humanBytes(received)} / ${humanBytes(total)}`:humanBytes(received);
      showCdnLoad({detail:`${t(src.offline?"assets_local":"cdn_downloading")} · ${amount}`,progress:fraction,indeterminate:fraction==null});
    },src.manifest?.["holistic.js"]?.sha256);
    if(!window.Holistic)throw new MediaPipeLoadError("MediaPipe Holistic did not initialize");
    showCdnLoad({detail:t("cdn_initializing"),indeterminate:true});
    const holistic=new window.Holistic({locateFile:file=>`${src.base}/${file}`});
    holistic.setOptions({modelComplexity:1,smoothLandmarks:true,enableSegmentation:false,
      smoothSegmentation:false,refineFaceLandmarks:false,minDetectionConfidence:0.5,minTrackingConfidence:0.5});
    holistic.onResults(results=>{
      videoImport.lastResults=results;
      if(videoImport.activeVideo)drawPose(videoImport.activeVideo,results.poseLandmarks||null);
    });
    videoImport.holistic=holistic;return holistic;
  }catch(error){throw error?.isMediaPipeLoad?error:new MediaPipeLoadError("MediaPipe initialization failed",error);}
}
function paintSkeleton(ctx,width,height,landmarks,{overlay=false}={}){
  ctx.lineWidth=Math.max(2,width/320);ctx.lineCap="round";
  ctx.strokeStyle=overlay?"#4ea8ff":"rgba(78,168,255,.92)";
  for(const [a,b] of POSE_CONNECTIONS){
    const p=landmarks[a],q=landmarks[b];
    if((p.visibility??1)<0.25||(q.visibility??1)<0.25)continue;
    ctx.beginPath();ctx.moveTo(p.x*width,p.y*height);ctx.lineTo(q.x*width,q.y*height);ctx.stroke();
  }
  const radius=Math.max(2.2,width/230);
  for(let index=0;index<landmarks.length;index++){
    const p=landmarks[index];
    if((p.visibility??1)<0.25)continue;
    const face=index<=10;
    ctx.beginPath();ctx.arc(p.x*width,p.y*height,face?radius*1.15:radius,0,Math.PI*2);
    if(face){
      ctx.strokeStyle="#ffa95c";ctx.lineWidth=1.4;ctx.stroke();
      ctx.lineWidth=Math.max(2,width/320);
      ctx.strokeStyle=overlay?"#4ea8ff":"rgba(78,168,255,.92)";
    }else{
      ctx.fillStyle="#eaf2ff";ctx.fill();
    }
  }
}
function drawPose(video, landmarks){
  const canvas=$("#poseCanvas"), ctx=canvas.getContext("2d");
  const vw=video.videoWidth||640, vh=video.videoHeight||360;
  canvas.width=Math.min(720,vw); canvas.height=Math.max(180,Math.round(canvas.width*vh/vw));
  ctx.clearRect(0,0,canvas.width,canvas.height);
  try{ ctx.drawImage(video,0,0,canvas.width,canvas.height); }catch(_e){}
  const kept=$("#poseSkeleton"), keptContext=kept?.getContext("2d");
  if(keptContext){
    kept.width=canvas.width;kept.height=canvas.height;
    keptContext.clearRect(0,0,kept.width,kept.height);
    keptContext.fillStyle="#060e1b";keptContext.fillRect(0,0,kept.width,kept.height);
  }
  if(!landmarks||landmarks.length!==33) return;
  $("#skeletonEmpty")?.classList.add("hidden");
  paintSkeleton(ctx,canvas.width,canvas.height,landmarks,{overlay:true});
  if(keptContext)paintSkeleton(keptContext,kept.width,kept.height,landmarks);
}
function poseArray(landmarks){
  if(!landmarks||landmarks.length!==33) return null;
  return landmarks.map(p=>[
    Number.isFinite(p.x)?p.x:0, Number.isFinite(p.y)?p.y:0, Number.isFinite(p.z)?p.z:0,
    Number.isFinite(p.visibility)?Math.max(0,Math.min(1,p.visibility)):1
  ]);
}
function fillMissingPose(frames){
  const valid=[]; frames.forEach((f,i)=>{if(f)valid.push(i);});
  if(valid.length<2) throw new Error(t("video_no_pose"));
  const prev=new Array(frames.length),next=new Array(frames.length); let p=-1,n=-1;
  for(let i=0;i<frames.length;i++){if(frames[i])p=i;prev[i]=p;}
  for(let i=frames.length-1;i>=0;i--){if(frames[i])n=i;next[i]=n;}
  return frames.map((f,i)=>{
    if(f) return f;
    const a=prev[i]>=0?prev[i]:next[i], b=next[i]>=0?next[i]:prev[i];
    const w=(a===b)?0:(i-a)/(b-a);
    return frames[a].map((v,j)=>[
      v[0]+(frames[b][j][0]-v[0])*w, v[1]+(frames[b][j][1]-v[1])*w,
      v[2]+(frames[b][j][2]-v[2])*w, 0
    ]);
  });
}
function waitForVideo(video,file){
  return new Promise((resolve,reject)=>{
    const url=URL.createObjectURL(file);
    const done=()=>{cleanup();resolve(url);}, fail=()=>{cleanup();URL.revokeObjectURL(url);reject(new Error(`Cannot decode ${file.name}`));};
    const cleanup=()=>{video.removeEventListener("loadeddata",done);video.removeEventListener("error",fail);};
    video.addEventListener("loadeddata",done,{once:true}); video.addEventListener("error",fail,{once:true});
    video.src=url; video.load();
  });
}
function seekVideo(video,time){
  const target=Math.max(0,Math.min(time,Math.max(0,video.duration-0.001)));
  if(Math.abs(video.currentTime-target)<0.001&&video.readyState>=2) return Promise.resolve();
  return new Promise((resolve,reject)=>{
    const ok=()=>{cleanup();resolve();}, bad=()=>{cleanup();reject(new Error("Video seek failed"));};
    const cleanup=()=>{video.removeEventListener("seeked",ok);video.removeEventListener("error",bad);};
    video.addEventListener("seeked",ok,{once:true});video.addEventListener("error",bad,{once:true});video.currentTime=target;
  });
}
function discardHolistic(){
  try{videoImport.holistic?.close?.();}catch(_e){}
  videoImport.holistic=null;videoImport.ready=false;videoImport.lastResults=null;
}
async function sendHolistic(holistic,video){
  let timer;const timeoutMs=videoImport.ready?30000:90000;
  try{
    await Promise.race([
      holistic.send({image:video}),
      new Promise((_,reject)=>{timer=setTimeout(()=>reject(new MediaPipeLoadError("MediaPipe model download or initialization timeout")),timeoutMs);})
    ]);
    if(!videoImport.ready){videoImport.ready=true;hideCdnLoad();}
  }catch(error){
    discardHolistic();
    throw error?.isMediaPipeLoad?error:new MediaPipeLoadError("MediaPipe WASM/model initialization failed",error);
  }finally{clearTimeout(timer);}
}
async function extractVideo(file,fileIndex,fileTotal){
  const video=$("#sourceVideo"), fps=Number($("#videoFps").value)||4;
  const url=await waitForVideo(video,file); videoImport.activeVideo=video;
  try{
    if(!Number.isFinite(video.duration)||video.duration<=0) throw new Error(`Invalid duration: ${file.name}`);
    const count=Math.min(12000,Math.max(2,Math.floor(video.duration*fps)+1));
    const step=video.duration/Math.max(1,count-1), frames=[]; let detected=0;
    $("#previewEmpty").classList.add("hidden");
    const holistic=await ensureHolistic();
    for(let i=0;i<count;i++){
      if(videoImport.cancelled) throw new Error("__cancelled__");
      await seekVideo(video,i*step); videoImport.lastResults=null;
      await sendHolistic(holistic,video);
      const pose=poseArray(videoImport.lastResults?.poseLandmarks); if(pose)detected++;
      frames.push(pose);
      const totalProgress=(fileIndex+(i+1)/count)/fileTotal;
      setExtractProgress(totalProgress,`${t("video_processing")}: ${file.name}`,`${i+1} / ${count} · pose ${detected}`);
      if(i%10===0) await new Promise(resolve=>setTimeout(resolve,0));
    }
    return fillMissingPose(frames);
  } finally {
    video.pause();video.removeAttribute("src");video.load();URL.revokeObjectURL(url);videoImport.activeVideo=null;
  }
}

$("#pickvideo").onclick=()=>$("#videoFiles").click();
$("#cancelVideo").onclick=()=>{videoImport.cancelled=true;};
async function runVideoBatch(files,dest){
  videoImport.cancelled=false; setVideoBusy(true); $("#extractLog").innerHTML=""; $("#s2msg").innerHTML="";
  videoImport.pendingFiles=files;videoImport.pendingDest=dest;
  appendExtractLog(`${t("video_output")} ${dest.path}`);
  let saved=0,cdnError=null;
  try{
    for(let i=0;i<files.length;i++){
      if(videoImport.cancelled) break;
      const file=files[i]; appendExtractLog(`${i+1}/${files.length} · ${file.name}`);
      try{
        const body=await extractVideo(file,i,files.length);
        setExtractProgress((i+0.98)/files.length,t("video_saving"),`${body.length} frames`);
        const r=await api().save_pose_npz(dest.path,$("#videoLabel").value,file.name,body);
        if(!r.ok) throw new Error(r.error); saved++; appendExtractLog(`✓ ${r.path}`);
      }catch(e){
        if(e.message==="__cancelled__")break;
        if(e.isMediaPipeLoad){
          cdnError=e;videoImport.pendingFiles=files.slice(i);appendExtractLog(`✗ ${cdnFailureDetail(e)}`,true);break;
        }
        appendExtractLog(`✗ ${file.name}: ${e.message}`,true);
      }
    }
    if(videoImport.cancelled){hideCdnLoad();setExtractProgress(0,t("video_cancelled"),"");msg("#s2msg","warn",t("video_cancelled"));}
    else if(cdnError){
      showCdnLoad({failed:true,detail:cdnFailureDetail(cdnError),retry:true});
      msg("#s2msg","bad",`${t("cdn_failed")}. ${t("cdn_help")}`);
    }
    else if(saved){
      hideCdnLoad();videoImport.pendingFiles=null;videoImport.pendingDest=null;
      setExtractProgress(1,`${t("video_done")}: ${saved}/${files.length}`,"");
      await scan(dest.path);
    }else{hideCdnLoad();msg("#s2msg","bad",isChinese()?t("video_no_output"):"No usable NPZ file was generated.");}
  } finally { setVideoBusy(false); }
}
$("#retryCdn").onclick=async()=>{
  if(!videoImport.pendingFiles?.length||!videoImport.pendingDest)return;
  discardHolistic();showCdnLoad({detail:t("cdn_connecting"),indeterminate:true});
  await runVideoBatch(videoImport.pendingFiles,videoImport.pendingDest);
};
$("#videoFiles").onchange=async event=>{
  const files=Array.from(event.target.files||[]); event.target.value=""; if(!files.length)return;
  const dest=await api().video_output();
  if(!dest.ok)return;
  videoOutput=dest;renderVideoOutput();
  await runVideoBatch(files,dest);
};
$("#changeVideoOutput").onclick=async()=>{
  const result=await api().pick_video_output();
  if(result?.ok){videoOutput=result;renderVideoOutput();}
};
$("#resetVideoOutput").onclick=async()=>{
  const result=await api().reset_video_output();
  if(result?.ok){videoOutput=result;renderVideoOutput();}
};

$("#pick").onclick=async()=>{
  const r=await api().pick_folder();
  if(!r.ok) return;
  await scan(r.path);
};
$("#gendemo").onclick=async()=>{
  $("#gendemo").disabled=true;
  const r=await api().generate_demo(sel.modality, 40);
  $("#gendemo").disabled=false;
  if(r.ok){ msg("#s2msg","warn",t("genok")); await scan(r.path); }
  else msg("#s2msg","bad",r.error);
};
async function scan(path){
  $("#foldbox").classList.remove("hidden");
  $("#foldpath").textContent=path; $("#foldkv").innerHTML=`<span class="spin"></span> ${t("scanning")}`;
  const r=await api().scan_folder(sel.modality, path);
  if(!r.ok){ $("#foldkv").innerHTML=""; msg("#s2msg","bad",r.error); $("#s2next").disabled=true; return; }
  sel.folder=path; sel.scan=r; $("#s2msg").innerHTML="";
  const tags=Object.entries(r.labels).map(([k,v])=>{
    const files=r.label_files?.[k];
    const detail=Number.isFinite(files)?`${files} ${t("files")} · ${v} ${t("found")}`:`${v}`;
    return `<span class="tag ${k.toLowerCase()==='asd'?'asd':'td'}">${k}: ${detail}</span>`;
  }).join("");
  const balanced=r.label_files&&Number(r.label_files.ASD)>0&&Number(r.label_files.TD)>0
    ? `<span class="tag ready">✓ ${t("supervised_ready")}</span>`:"";
  $("#foldkv").innerHTML=`<span><b>${r.n_samples}</b> ${t("found")}</span><span><b>${r.n_files}</b> ${t("files")}</span>`+
    `<span><b>${r.n_features}</b> ${t("feats")}</span><span>${tags}${balanced}</span>`;
  $("#s2next").disabled=false;
  updateConsoleChrome();
}
$("#s2next").onclick=()=>{ if(!$("#nodeid").value) $("#nodeid").value="node_1"; goStep(3); };

$("#testconn").onclick=async()=>{
  const coord=$("#coord").value.trim(); if(!coord){msg("#s3msg","bad","enter a coordinator URL");return;}
  const key=$("#passwd").value.trim();
  msg("#s3msg","warn",`<span class="spin"></span> ${t("connecting")}`);
  const r=await api().test_connect(coord, sel.modality, key, sel.invitation);
  if(!r.ok){ msg("#s3msg","bad",r.error); $("#s3next").disabled=true; setConn("off",""); return; }
  sel.sch=r;
  renderPrivacyCopy();
  const host=coord.replace(/^https?:\/\//,"");
  const featOk = r.n_features===sel.scan.n_features;
  const info=r.modality_info?(isTraditional()?HANT_MODALITIES[r.modality_info.key]?.task:(isChinese()?r.modality_info.task_zh:r.modality_info.task_en)):r.modality;
  const privacy=r.secure_aggregation?t("mode_secure"):t("mode_solo_dp");
  let lines=`<b>${info||"—"}</b> · ${r.n_features} ${t("feats")} · cohort ${r.cohort} · ${privacy} · ε/round ${r.dp.epsilon_per_round}, budget ${r.epsilon_budget}`;
  if(r.pinned) lines+=`<br>${t("pin_ok")}`;
  if(r.pin_warning) lines+=`<br>⚠ ${r.pin_warning}`;
  if(!r.compatible){ msg("#s3msg","bad",`${t("compat_bad")}<br>${lines}`); $("#s3next").disabled=true; setConn("off",""); }
  else if(!featOk){ msg("#s3msg","bad",`${t("mismatch_feat")}<br>${lines}`); $("#s3next").disabled=true; setConn("off",""); }
  else if(r.invitation_required && !sel.invitation){ msg("#s3msg","bad",`${t("invitation_missing")}<br>${lines}`); $("#s3next").disabled=true; setConn("off",""); }
  else { msg("#s3msg","ok",`${t("compat_ok")}<br>${lines}`); $("#s3next").disabled=false; setConn("on",host); }
  updateConsoleChrome();
};

let pollTimer=null;
$("#s3next").onclick=async()=>{
  const cfg={ coord:$("#coord").value.trim(), key:$("#passwd").value.trim(),
    node_id:($("#nodeid").value.trim()||"node_1"),
    name:$("#nodename").value.trim(), folder:sel.folder, modality:sel.modality,
    rounds:+$("#rounds").value||5, seed:1, invitation:sel.invitation||null };
  $("#rsSamp").textContent=sel.scan.n_samples;
  $("#rsRound").textContent="0"; $("#rsFed").textContent="—"; $("#rsEps").textContent="0";
  $("#epsFill").style.width="0"; renderTraffic(null);
  $("#rsMetric").textContent=(sel.sch.primary_metric||"acc").toUpperCase();
  $("#log").textContent=""; $("#s4msg").innerHTML=""; $("#restart").classList.add("hidden");
  $("#stop").classList.remove("hidden"); $("#stop").disabled=false;
  setConn("run"); goStep(4);
  const r=await api().start(cfg);
  if(!r.ok){ msg("#s4msg","bad",r.error); setConn("on"); return; }
  if(pollTimer) clearInterval(pollTimer);
  pollTimer=setInterval(poll, 500);
};
async function poll(){
  const p=await api().poll(); const st=p.state, s=st.summary;
  const el=$("#log"); el.innerHTML=p.log.map(l=>{
    const cls=/round|masked/.test(l)?' class="r"':''; return `<span${cls}>${l.replace(/</g,"&lt;")}</span>`;
  }).join("\n"); el.scrollTop=el.scrollHeight;
  if(s){
    $("#rsRound").textContent=s.current_round||s.rounds_done||0;
    const v=s.fed_primary; $("#rsFed").textContent=(typeof v==="number")?v.toFixed(3):"…";
    $("#rsEps").textContent=(s.global_eps??0);
    const bud=sel.sch?.epsilon_budget||10; $("#epsFill").style.width=Math.min(100,100*(s.global_eps||0)/bud)+"%";
    $("#stEps").textContent=`ε ${s.global_eps??0} / ${bud}`;
    renderTraffic(s);
  }
  document.dispatchEvent(new CustomEvent("gbadf:run",{detail:{state:st,summary:s}}));
  if(st.done){
    clearInterval(pollTimer); pollTimer=null;
    $("#stop").classList.add("hidden"); $("#restart").classList.remove("hidden");
    setConn(st.error?"on":"done");
    if(st.error) msg("#s4msg","bad",st.error);
    else msg("#s4msg","ok","✓ "+t(sel.sch?.secure_aggregation!==false?"train_done":"train_done_solo"));
    updateConsoleChrome();
  }
}
$("#stop").onclick=async()=>{ $("#stop").disabled=true; await api().stop(); };
$("#restart").onclick=()=>goStep(3);

async function init(){
  try{ MODS=await api().list_modalities(); }catch(e){ MODS=[]; }
  await refreshVideoOutput();
  try{ const d=await api().defaults();
    if(d){ $("#coord").value=d.coord||""; $("#nodeid").value=d.node_id||"node_1"; } }catch(e){}
  applyTheme(currentTheme(),{persist:false});
  applyLang();
  goStep(1);
}
window.addEventListener("pywebviewready", init);
// fallback if opened in a plain browser (no pywebview): still render UI
setTimeout(()=>{ if(!MODS.length && window.pywebview) init(); }, 300);
