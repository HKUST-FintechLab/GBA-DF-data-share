const I18N = window.GBA_DF_I18N;
let LANG="en", MODS=[], sel={modality:null, mInfo:null, folder:null, scan:null, sch:null, invitation:null};
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
  neuro:{name:"EEG／fMRI 神經影像", task:"神經影像篩查 (ASD/TD)", hint:"每次掃描一個 .npz（鍵 'ts'，通道×時間）或 CSV，置於 asd/ 與 td/ 子資料夾"}
};

function applyLang(){
  document.querySelectorAll("[data-i]").forEach(el=>{ const k=el.getAttribute("data-i"); if(I18N[LANG][k]!=null) el.textContent=I18N[LANG][k]; });
  document.querySelectorAll("[data-i-placeholder]").forEach(el=>{ const k=el.getAttribute("data-i-placeholder"); if(I18N[LANG][k]!=null) el.placeholder=I18N[LANG][k]; });
  $("#zhHans").classList.toggle("on",LANG==="zh"); $("#zhHant").classList.toggle("on",LANG==="zh-Hant"); $("#en").classList.toggle("on",LANG==="en");
  document.documentElement.lang = LANG;
  renderMods(); renderSteps(); renderScene(); updateActionControls(); renderStatus();
}
$("#zhHans").onclick=()=>{LANG="zh";applyLang();};
$("#zhHant").onclick=()=>{LANG="zh-Hant";applyLang();};
$("#en").onclick=()=>{LANG="en";applyLang();};

function renderStatus(){
  const map={off:"st_off",on:"st_on",run:"st_run",done:"st_done"};
  const dot=$("#stDot"); dot.className="dot"+(conn.state==="on"||conn.state==="done"?" on":(conn.state==="run"?" busy":""));
  $("#stConn").textContent = t(map[conn.state]) + (conn.host?` · ${conn.host}`:"");
}
function setConn(state, host){ conn.state=state; if(host!=null) conn.host=host; renderStatus(); }
function renderTraffic(s){
  const total=s?.application_bytes_sent||0, masked=s?.masked_payload_bytes_sent||0;
  const metadata=s?.protocol_metadata_bytes_sent||0;
  $("#rsTx").textContent=humanBytes(total);
  $("#rsTxDetail").textContent=`${t("tx_masked")} ${humanBytes(masked)} · ${t("tx_metadata")} ${humanBytes(metadata)}`;
  $("#stShared").textContent=total?t("st_shared_bytes").replace("{bytes}",humanBytes(total)):t("st_shared");
}

const STEP_LABELS={en:["Data type","Folder","Connect","Train"],zh:["数据类型","文件夹","连接","训练"],"zh-Hant":["資料類型","資料夾","連線","訓練"]};
let curStep=1;
/* what each completed step actually decided — the rail doubles as a running summary, so the
   room can see the whole configuration at a glance instead of only which step is open */
function stepState(n){
  if(n>curStep) return "";                 // nothing decided yet — a prefilled default is not a state
  if(n===1) return sel.mInfo ? (isTraditional()?HANT_MODALITIES[sel.mInfo.key].name
    :(isChinese()?sel.mInfo.zh:sel.mInfo.en)) : "";
  if(n===2) return sel.scan ? `${sel.scan.n_samples} · ${sel.scan.n_features}f` : "";
  if(n===3){ try{ return conn.host || new URL($("#coord").value.trim()).hostname; }catch(_e){ return ""; } }
  if(n===4) return $("#rsRound")?.textContent && $("#rsRound").textContent!=="0"
    ? `r${$("#rsRound").textContent} · ε ${$("#rsEps").textContent}` : "";
  return "";
}
const SCENE_KEYS=[null,"s1","s2","s3","s4"];
function renderSteps(){
  const s=$("#steps"); s.innerHTML="";
  STEP_LABELS[LANG].forEach((lb,i)=>{
    const n=i+1, d=document.createElement("i");
    d.className=(n===curStep?"on":"")+(n<curStep?" done":"");
    d.title=lb+(stepState(n)?` · ${stepState(n)}`:"");
    if(n<curStep) d.onclick=()=>goStep(n);          // completed scenes stay revisitable
    s.appendChild(d);
  });
}
/* The caption is the page's only heading: scene index, one plain-language line, one detail line.
   It replaces the old per-step <h2> + hint, so nothing is stated twice. */
function renderScene(){
  const k=SCENE_KEYS[curStep], st=stepState(curStep);
  $("#sceneIdx").innerHTML=`<b>0${curStep}</b> / ${STEP_LABELS[LANG][curStep-1].toUpperCase()}`+
    (st?` &nbsp;·&nbsp; ${st.replace(/</g,"&lt;")}`:"");
  $("#sceneTitle").textContent=t(`${k}_h`);
  $("#sceneSub").textContent = curStep===2 ? (sel.mInfo?sceneHintForModality():t("s2_note"))
    : t(curStep===4?"s4_banner":`${k}_hint`);
}
function goStep(n){
  curStep=n;
  document.querySelectorAll(".scene").forEach(el=>el.classList.toggle("hidden",+el.getAttribute("data-step")!==n));
  document.body.className=document.body.className.replace(/step\d/g,"").trim()+" step"+n;
  // the bottom strip changes its verb with the scene
  $("#backBtn").disabled = n===1 || n===4;
  $("#s2next").classList.toggle("hidden", n>=3);
  $("#s3next").classList.toggle("hidden", n!==3);
  $("#s2next").disabled = n===1 ? !sel.modality : !sel.scan;
  $("#s2next").classList.toggle("go", !$("#s2next").disabled);   // the only forward move, lit
  renderSteps(); renderScene(); stageScene(n);
}
$("#backBtn").onclick=()=>{ if(curStep>1) goStep(curStep-1); };
$("#s2next").onclick=()=>{
  if(curStep===1&&sel.modality) goStep(2);
  else if(curStep===2&&sel.scan){ if(!$("#nodeid").value) $("#nodeid").value="node_1"; goStep(3); }
};

/* Each modality gets a small live sketch of what its data actually looks like — a gaze
   scan-path, a walking skeleton, a multichannel trace. It reads faster than a label for a
   non-technical room, and it is drawn, not stock art, so it stays on palette. */
const MOD_SKETCH={
  /* A real gaze plot over a face: fixations sized by dwell, joined by saccades. The path
     lingers on the mouth and skims the eyes, which is the actual signal social-attention
     screening looks for — so the picture states the task instead of decorating it. */
  eyegaze(ctx,w,h,tm,on){
    const cx=w/2, cy=h*.5, fw=w*.20, fh=h*.30;
    const ink=on?"rgba(78,168,255,":"rgba(122,168,235,";
    ctx.strokeStyle=ink+(on?".3":".18")+")"; ctx.lineWidth=1;
    ctx.beginPath(); ctx.ellipse(cx,cy,fw,fh,0,0,Math.PI*2); ctx.stroke();     // face
    const eyeL=[cx-fw*.42,cy-fh*.22], eyeR=[cx+fw*.42,cy-fh*.22], mouth=[cx,cy+fh*.44];
    [eyeL,eyeR].forEach(([x,y])=>{                                            // eyes
      ctx.beginPath(); ctx.ellipse(x,y,fw*.26,fh*.12,0,0,Math.PI*2); ctx.stroke();
      ctx.beginPath(); ctx.arc(x,y,fh*.055,0,Math.PI*2);
      ctx.fillStyle=ink+(on?".55":".3")+")"; ctx.fill();
    });
    ctx.beginPath(); ctx.moveTo(mouth[0]-fw*.3,mouth[1]);                      // mouth
    ctx.quadraticCurveTo(mouth[0],mouth[1]+fh*.12,mouth[0]+fw*.3,mouth[1]); ctx.stroke();

    // fixation sequence: mostly mouth, a glance at each eye — dwell drives the radius
    const targets=[[mouth,7],[mouth,6],[eyeL,3],[mouth,8],[eyeR,3],[mouth,6],[eyeL,2.5]];
    const pts=targets.map(([[x,y],d],i)=>[x+Math.sin(tm*.7+i*2.1)*fw*.16,
                                          y+Math.cos(tm*.6+i*1.7)*fh*.13, d]);
    ctx.strokeStyle=ink+(on?".45":".25")+")"; ctx.lineWidth=1;
    ctx.beginPath(); pts.forEach((p,i)=>i?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1])); ctx.stroke();
    const live=Math.floor(tm*1.4)%pts.length;
    pts.forEach((p,i)=>{
      const hot=i===live;
      ctx.beginPath(); ctx.arc(p[0],p[1],p[2]*(hot?1.35:1),0,Math.PI*2);
      ctx.fillStyle=ink+(on?(hot?".4":".16"):".1")+")"; ctx.fill();
      ctx.strokeStyle=ink+(on?(hot?".95":".5"):".32")+")"; ctx.lineWidth=hot?1.4:1; ctx.stroke();
    });
  },

  /* The MediaPipe topology the client actually extracts — 33 landmarks, real joints, real
     bones. Face points are drawn hollow and warm because they are the identity-bearing ones
     the pipeline throws away; the body is what it keeps. */
  action(ctx,w,h,tm,on){
    const cx=w/2, top=h*.14, s=h*.155, sw=Math.sin(tm*1.9), sw2=Math.cos(tm*1.9);
    const P={};
    const set=(i,x,y)=>P[i]=[x,y];
    set(0,cx,top+s*.34);                                                       // nose
    set(2,cx-s*.13,top+s*.24); set(5,cx+s*.13,top+s*.24);                      // eyes
    set(7,cx-s*.26,top+s*.30); set(8,cx+s*.26,top+s*.30);                      // ears
    set(11,cx-s*.52,top+s*.95); set(12,cx+s*.52,top+s*.95);                    // shoulders
    set(13,cx-s*.80+sw*s*.14,top+s*1.55); set(14,cx+s*.80-sw*s*.14,top+s*1.55);// elbows
    set(15,cx-s*.92+sw*s*.30,top+s*2.15); set(16,cx+s*.92-sw*s*.30,top+s*2.15);// wrists
    set(23,cx-s*.34,top+s*2.05); set(24,cx+s*.34,top+s*2.05);                  // hips
    set(25,cx-s*.40+sw2*s*.16,top+s*2.90); set(26,cx+s*.40-sw2*s*.16,top+s*2.90); // knees
    set(27,cx-s*.44+sw2*s*.30,top+s*3.70); set(28,cx+s*.44-sw2*s*.30,top+s*3.70); // ankles
    const BONES=[[11,12],[11,13],[13,15],[12,14],[14,16],[11,23],[12,24],[23,24],
                 [23,25],[25,27],[24,26],[26,28],[0,2],[2,7],[0,5],[5,8]];
    ctx.globalAlpha=on?1:.5; ctx.lineCap="round";
    ctx.strokeStyle=on?"#4EA8FF":"#7AA8EB"; ctx.lineWidth=1.5;
    BONES.forEach(([a,b])=>{ if(!P[a]||!P[b])return;
      ctx.beginPath(); ctx.moveTo(...P[a]); ctx.lineTo(...P[b]); ctx.stroke(); });
    Object.entries(P).forEach(([i,[x,y]])=>{
      const face=+i<=10;
      ctx.beginPath(); ctx.arc(x,y,face?2.6:2.9,0,Math.PI*2);
      if(face){ ctx.strokeStyle="#FFA95C"; ctx.lineWidth=1.2; ctx.stroke();
                ctx.strokeStyle=on?"#4EA8FF":"#7AA8EB"; ctx.lineWidth=1.5; }
      else { ctx.fillStyle=on?"#EAF2FF":"#A3B9D8"; ctx.fill(); }
    });
    ctx.globalAlpha=1;
  },
  neuro(ctx,w,h,tm,on){
    const col=on?"rgba(78,168,255,":"rgba(122,168,235,";
    for(let c=0;c<4;c++){
      const y=h*(.28+c*.15);
      ctx.strokeStyle=col+(on?.75-c*.13:.4-c*.07)+")"; ctx.lineWidth=1.1;
      ctx.beginPath();
      for(let x=w*.14;x<=w*.86;x+=2){
        const p=(x/w)*9+tm*(1.6+c*.35)+c*2;
        ctx.lineTo(x,y+Math.sin(p)*h*.045+Math.sin(p*2.7+c)*h*.028);
      }
      ctx.stroke();
    }
  }
};
/* ======================= the stage =======================================
   One full-bleed canvas. Each step paints a scene on it; the DOM only carries the
   controls that need to be typed into or clicked. Scene 1's three sketches are laid
   out here, and .picks buttons are positioned on top of them as the hit targets so
   the choice stays keyboard-reachable. */
const STAGE={cv:null,ctx:null,W:0,H:0,DPR:1,clock:0,last:0,raf:null,scene:1,slots:[]};
function stageLayout(){
  const cv=STAGE.cv; if(!cv) return;
  STAGE.DPR=Math.min(window.devicePixelRatio||1,2);
  STAGE.W=cv.clientWidth; STAGE.H=cv.clientHeight;
  cv.width=Math.max(1,Math.round(STAGE.W*STAGE.DPR)); cv.height=Math.max(1,Math.round(STAGE.H*STAGE.DPR));
  STAGE.ctx.setTransform(STAGE.DPR,0,0,STAGE.DPR,0,0);
  layoutPicks();
}
function pickSlots(){
  const {W,H}=STAGE, n=Math.max(1,MODS.length);
  const boxW=Math.min(300,(W*0.78)/n), gap=Math.min(70,W*0.05);
  const total=boxW*n+gap*(n-1), x0=(W-total)/2, cy=H*0.36;
  return MODS.map((m,i)=>({key:m.key,x:x0+i*(boxW+gap),y:cy-110,w:boxW,h:220,cx:x0+i*(boxW+gap)+boxW/2,cy}));
}
function layoutPicks(){
  const box=$("#mods"); if(!box) return;
  STAGE.slots=pickSlots();
  [...box.children].forEach((b,i)=>{
    const s=STAGE.slots[i]; if(!s) return;
    b.style.left=`${s.x}px`; b.style.top=`${s.y}px`; b.style.width=`${s.w}px`; b.style.height=`${s.h}px`;
  });
}
function drawScenePick(ctx,tm){
  const {W,H}=STAGE;
  STAGE.slots.forEach((s,i)=>{
    const m=MODS[i]; if(!m) return;
    const on=sel.modality===m.key, dim=sel.modality&&!on;
    ctx.save();
    ctx.globalAlpha=dim?0.3:1;
    ctx.translate(s.cx-s.w/2,s.cy-92);
    (MOD_SKETCH[m.key]||(()=>{}))(ctx,s.w,150,tm,on);
    ctx.restore();

    const localized=isTraditional()?HANT_MODALITIES[m.key]:null;
    const nm=localized?.name||(isChinese()?m.zh:m.en);
    const tk=localized?.task||(isChinese()?m.task_zh:m.task_en);
    ctx.textAlign="center"; ctx.globalAlpha=dim?0.4:1;
    ctx.font=`300 ${Math.round(Math.min(26,s.w*0.115))}px ${SERIF_STACK}`;
    ctx.fillStyle=on?"#EAF1FC":"#A3B9D8";
    ctx.fillText(nm,s.cx,s.cy+72);
    ctx.font=`10px ${MONO_STACK}`; ctx.fillStyle="#66809F";
    ctx.fillText(tk,s.cx,s.cy+94);
    ctx.font=`9px ${MONO_STACK}`; ctx.fillStyle=on?"#4EA8FF":"#3C6FA8";
    ctx.fillText(`${m.n_features} ${t("feats")}`.toUpperCase().split("").join(" "),s.cx,s.cy+116);
    // the selected sketch gets the console's corner ticks
    if(on){
      ctx.strokeStyle="#4EA8FF"; ctx.lineWidth=1; const p=12, x=s.cx-s.w/2, y=s.cy-108, w=s.w, h=246;
      [[x,y,1,1],[x+w,y,-1,1],[x,y+h,1,-1],[x+w,y+h,-1,-1]].forEach(([px,py,sx,sy])=>{
        ctx.beginPath(); ctx.moveTo(px+sx*p,py); ctx.lineTo(px,py); ctx.lineTo(px,py+sy*p); ctx.stroke();
      });
    }
    ctx.globalAlpha=1;
  });
}
const SERIF_STACK="'Newsreader','Noto Serif SC',Georgia,serif";
const MONO_STACK="'IBM Plex Mono',Consolas,monospace";

/* Scene 2: the recordings this node holds, as warm points that accumulate as the folder
   is scanned. They orbit slowly and never leave the ring — the same grammar as the
   coordinator console, so the two surfaces read as one system. */
function drawSceneData(ctx,tm){
  const {W,H}=STAGE, cx=W*0.30, cy=H*0.5, R=Math.min(W,H)*0.19;
  ctx.strokeStyle="rgba(122,168,235,.18)"; ctx.lineWidth=1;
  ctx.beginPath(); ctx.arc(cx,cy,R,0,Math.PI*2); ctx.stroke();
  const n=sel.scan?Math.min(90,Math.max(6,Math.round(sel.scan.n_samples/5))):0;
  for(let i=0;i<n;i++){
    const a=i*2.399963+tm*0.06, r=Math.sqrt(i/Math.max(1,n))*R*0.86;
    blitStage(ctx,STAGE_SPR.warm,cx+Math.cos(a)*r,cy+Math.sin(a)*r,8,0.85);
  }
  ctx.textAlign="center"; ctx.font=`10px ${MONO_STACK}`; ctx.fillStyle="#9A6636";
  ctx.fillText((sel.scan?`${sel.scan.n_samples} ${t("found")}`:t("s2_empty")).toUpperCase().split("").join(" "),
    cx,cy+R+34);
}

/* Scene 3: this node, and the coordinator it is about to speak to. */
function drawSceneConnect(ctx,tm){
  const {W,H}=STAGE, y=H*0.46, ax=W*0.20, bx=W*0.46, r=Math.min(W,H)*0.075;
  const live=conn.state==="on"||conn.state==="done"||conn.state==="run";
  ctx.setLineDash([4,6]);
  ctx.strokeStyle=live?"rgba(78,168,255,.5)":"rgba(122,168,235,.14)"; ctx.lineWidth=1;
  ctx.beginPath(); ctx.moveTo(ax+r,y); ctx.lineTo(bx-r,y); ctx.stroke(); ctx.setLineDash([]);
  if(live) blitStage(ctx,STAGE_SPR.azure,ax+r+((bx-ax-2*r)*((tm*0.35)%1)),y,16,0.8);
  [[ax,t("c_this"),"#FFA95C",true],[bx,t("c_coord"),live?"#4EA8FF":"#3C6FA8",false]].forEach(([x,label,col,warm])=>{
    ctx.beginPath(); ctx.arc(x,y,r,0,Math.PI*2);
    ctx.fillStyle="rgba(14,26,45,.9)"; ctx.fill();
    ctx.strokeStyle=col; ctx.lineWidth=1.3; ctx.stroke();
    if(warm) for(let i=0;i<12;i++){
      const a=i*2.399963, rr=Math.sqrt(i/12)*r*0.7;
      blitStage(ctx,STAGE_SPR.warm,x+Math.cos(a)*rr,y+Math.sin(a)*rr,7,0.8);
    }
    ctx.textAlign="center"; ctx.font=`9px ${MONO_STACK}`; ctx.fillStyle="#66809F";
    ctx.fillText(label.toUpperCase().split("").join(" "),x,y+r+26);
  });
}

function stageGlow(r,g,b){
  const S=48,c=document.createElement("canvas"); c.width=c.height=S;
  const x=c.getContext("2d"), gr=x.createRadialGradient(S/2,S/2,0,S/2,S/2,S/2);
  gr.addColorStop(0,"rgba(255,255,255,.9)"); gr.addColorStop(.2,`rgba(${r},${g},${b},.8)`);
  gr.addColorStop(.55,`rgba(${r},${g},${b},.18)`); gr.addColorStop(1,`rgba(${r},${g},${b},0)`);
  x.fillStyle=gr; x.fillRect(0,0,S,S); return c;
}
const STAGE_SPR={warm:stageGlow(255,169,92),bone:stageGlow(234,242,255),azure:stageGlow(78,168,255)};
function blitStage(ctx,spr,x,y,size,alpha){
  ctx.globalAlpha=alpha; ctx.drawImage(spr,x-size/2,y-size/2,size,size); ctx.globalAlpha=1;
}

function stageDraw(ts){
  const ctx=STAGE.ctx; if(!ctx) return;
  const dt=STAGE.last?Math.min(0.05,(ts-STAGE.last)/1000):0.016; STAGE.last=ts; STAGE.clock+=dt;
  if(!STAGE.W||STAGE.W!==STAGE.cv.clientWidth||STAGE.H!==STAGE.cv.clientHeight) stageLayout();
  ctx.clearRect(0,0,STAGE.W,STAGE.H);
  const g=ctx.createRadialGradient(STAGE.W*.5,STAGE.H*.36,0,STAGE.W*.5,STAGE.H*.36,Math.max(STAGE.W,STAGE.H)*.72);
  g.addColorStop(0,"#1B3155"); g.addColorStop(1,"#0D1A2E");
  ctx.fillStyle=g; ctx.fillRect(0,0,STAGE.W,STAGE.H);
  if(STAGE.scene===1) drawScenePick(ctx,STAGE.clock);
  else if(STAGE.scene===2) drawSceneData(ctx,STAGE.clock);
  else if(STAGE.scene===3) drawSceneConnect(ctx,STAGE.clock);
  else if(STAGE.scene===4) drawScenePipeline(ctx,dt);
  STAGE.raf=requestAnimationFrame(stageDraw);
}
function stageScene(n){ STAGE.scene=n; if(n===1) layoutPicks(); }
function stageStart(){
  STAGE.cv=$("#stage"); if(!STAGE.cv) return;
  STAGE.ctx=STAGE.cv.getContext("2d"); stageLayout();
  if(!STAGE.raf) STAGE.raf=requestAnimationFrame(stageDraw);
}
window.addEventListener("resize",stageLayout);

function renderMods(){
  const box=$("#mods"); box.innerHTML="";
  MODS.forEach(m=>{
    const localized=isTraditional()?HANT_MODALITIES[m.key]:null;
    const nm=localized?.name||(isChinese()?m.zh:m.en);
    const b=document.createElement("button");
    b.className="pick"; b.type="button"; b.textContent=nm; b.setAttribute("aria-pressed",String(sel.modality===m.key));
    b.onclick=()=>{ if(videoImport.running) return;
      sel.modality=m.key; sel.mInfo=m; sel.folder=null; sel.scan=null;
      $("#foldbox").classList.add("hidden"); $("#s2msg").innerHTML="";
      renderMods(); updateActionControls(); goStep(2); };
    box.appendChild(b);
  });
  layoutPicks();
}
function sceneHintForModality(){
  if(!sel.mInfo) return t("s2_note");
  return isTraditional()?HANT_MODALITIES[sel.mInfo.key].hint:
    (isChinese()?sel.mInfo.file_hint.split("·")[0]:sel.mInfo.file_hint.split("·")[1]||sel.mInfo.file_hint);
}
function updateS2Hint(){ if(curStep===2) renderScene(); }
function updateActionControls(){
  const action=sel.modality==="action";
  $("#pickvideo").classList.toggle("hidden",!action);
  $("#videoImport").classList.toggle("hidden",!action);
  $("#pick").textContent=action?t("pick_npz"):t("pick");
}

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
document.addEventListener("keydown",event=>{ if(event.key==="Escape"&&!$("#configModal").classList.contains("hidden")) closeConfigImport(); });

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
  ["#pick","#pickvideo","#gendemo","#videoLabel","#videoFps"].forEach(s=>$(s).disabled=busy);
  $("#cancelVideo").classList.toggle("hidden",!busy);
  $("#s2next").disabled=busy||!sel.scan;
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
/* Paint the skeleton twice: over the frame on the left, and alone on the right. The right pane
   is the honest one — it is literally the only thing that survives the video. */
function paintSkeleton(ctx,W,H,landmarks,{overlay}){
  ctx.lineWidth=Math.max(2,W/320); ctx.lineCap="round";
  ctx.strokeStyle=overlay?"#4EA8FF":"rgba(78,168,255,.92)";
  for(const [a,b] of POSE_CONNECTIONS){
    const p=landmarks[a],q=landmarks[b];
    if((p.visibility??1)<0.25||(q.visibility??1)<0.25) continue;
    ctx.beginPath(); ctx.moveTo(p.x*W,p.y*H); ctx.lineTo(q.x*W,q.y*H); ctx.stroke();
  }
  const r=Math.max(2.2,W/230);
  for(let i=0;i<landmarks.length;i++){
    const p=landmarks[i];
    if((p.visibility??1)<0.25) continue;
    // the face points are the identity-bearing ones: hollow, warm, and never filled in
    const face=i<=10;
    ctx.beginPath(); ctx.arc(p.x*W,p.y*H,face?r*1.15:r,0,Math.PI*2);
    if(face){ ctx.strokeStyle="#FFA95C"; ctx.lineWidth=1.4; ctx.stroke(); ctx.lineWidth=Math.max(2,W/320); ctx.strokeStyle=overlay?"#4EA8FF":"rgba(78,168,255,.92)"; }
    else { ctx.fillStyle="#EAF2FF"; ctx.fill(); }
  }
}
function drawPose(video, landmarks){
  const canvas=$("#poseCanvas"), ctx=canvas.getContext("2d");
  const vw=video.videoWidth||640, vh=video.videoHeight||360;
  canvas.width=Math.min(720,vw); canvas.height=Math.max(180,Math.round(canvas.width*vh/vw));
  ctx.clearRect(0,0,canvas.width,canvas.height);
  try{ ctx.drawImage(video,0,0,canvas.width,canvas.height); }catch(_e){}

  const keep=$("#poseSkeleton"), kctx=keep?.getContext("2d");
  if(kctx){
    keep.width=canvas.width; keep.height=canvas.height;
    kctx.clearRect(0,0,keep.width,keep.height);
    kctx.fillStyle="#060E1B"; kctx.fillRect(0,0,keep.width,keep.height);
  }
  if(!landmarks||landmarks.length!==33) return;
  $("#skeletonEmpty")?.classList.add("hidden");
  paintSkeleton(ctx,canvas.width,canvas.height,landmarks,{overlay:true});
  if(kctx) paintSkeleton(kctx,keep.width,keep.height,landmarks,{overlay:false});
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
  const dest=sel.folder?{ok:true,path:sel.folder}:await api().pick_folder();
  if(!dest.ok)return;
  await runVideoBatch(files,dest);
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
  const tags=Object.entries(r.labels).map(([k,v])=>`<span class="tag ${k.toLowerCase()==='asd'?'asd':'td'}">${k}: ${v}</span>`).join("");
  $("#foldkv").innerHTML=`<span><b>${r.n_samples}</b> ${t("found")}</span><span><b>${r.n_files}</b> ${t("files")}</span>`+
    `<span><b>${r.n_features}</b> ${t("feats")}</span><span>${tags}</span>`;
  $("#s2next").disabled=false; $("#s2next").classList.add("go"); renderSteps(); renderScene();
}

$("#testconn").onclick=async()=>{
  const coord=$("#coord").value.trim(); if(!coord){msg("#s3msg","bad","enter a coordinator URL");return;}
  const key=$("#passwd").value.trim();
  msg("#s3msg","warn",`<span class="spin"></span> ${t("connecting")}`);
  const r=await api().test_connect(coord, sel.modality, key, sel.invitation);
  if(!r.ok){ msg("#s3msg","bad",r.error); $("#s3next").disabled=true; setConn("off",""); return; }
  sel.sch=r;
  const host=coord.replace(/^https?:\/\//,"");
  const featOk = r.n_features===sel.scan.n_features;
  const info=r.modality_info?(isTraditional()?HANT_MODALITIES[r.modality_info.key]?.task:(isChinese()?r.modality_info.task_zh:r.modality_info.task_en)):r.modality;
  let lines=`<b>${info||"—"}</b> · ${r.n_features} ${t("feats")} · cohort ${r.cohort} · ε/round ${r.dp.epsilon_per_round}, budget ${r.epsilon_budget}`;
  if(r.pinned) lines+=`<br>${t("pin_ok")}`;
  if(r.pin_warning) lines+=`<br>⚠ ${r.pin_warning}`;
  if(!r.compatible){ msg("#s3msg","bad",`${t("compat_bad")}<br>${lines}`); $("#s3next").disabled=true; setConn("off",""); }
  else if(!featOk){ msg("#s3msg","bad",`${t("mismatch_feat")}<br>${lines}`); $("#s3next").disabled=true; setConn("off",""); }
  else if(r.invitation_required && !sel.invitation){ msg("#s3msg","bad",`${t("invitation_missing")}<br>${lines}`); $("#s3next").disabled=true; setConn("off",""); }
  else { msg("#s3msg","ok",`${t("compat_ok")}<br>${lines}`); $("#s3next").disabled=false; setConn("on",host); }
};

/* ===================== local pipeline visualisation =====================
   Five stages, and one boundary. Material is warm while it is still identifying
   (recordings, feature rows), bone once it is only structure (leaf counts), and
   azure once it is masked. Only azure crosses the "this machine" line — that is the
   whole claim, drawn rather than asserted. Colours match the coordinator console. */
const PIPE={W:0,H:0,parts:[],stages:[],boundaryX:0,
  data:{samples:0,features:0,cells:0,bytes:0,round:0}};
const PIPE_KEYS=["p_records","p_features","p_leaves","p_masked","p_sent"];
const PIPE_TINT={warm:"#FFA95C",bone:"#EAF2FF",azure:"#4EA8FF"};
const PIPE_TONE=["warm","warm","bone","azure","azure"];

function pipeGlow(r,g,b){
  const S=48,c=document.createElement("canvas"); c.width=c.height=S;
  const x=c.getContext("2d"), gr=x.createRadialGradient(S/2,S/2,0,S/2,S/2,S/2);
  gr.addColorStop(0,"rgba(255,255,255,.9)"); gr.addColorStop(.2,`rgba(${r},${g},${b},.8)`);
  gr.addColorStop(.55,`rgba(${r},${g},${b},.18)`); gr.addColorStop(1,`rgba(${r},${g},${b},0)`);
  x.fillStyle=gr; x.fillRect(0,0,S,S); return c;
}
const PIPE_SPR={warm:pipeGlow(255,169,92),bone:pipeGlow(234,242,255),azure:pipeGlow(78,168,255)};

function pipeLayout(){
  // the pipeline runs across the lower half of the stage, clear of the caption and figures
  const W=STAGE.W, H=STAGE.H;
  PIPE.W=W; PIPE.H=H;
  // stop short of the figures column on the right, which is a fixed 330px panel
  const left=W*0.055, right=W-Math.min(370,W*0.30);
  PIPE.boundaryX=left+(right-left)*0.72;
  const first=left+30, last=PIPE.boundaryX-64, step=(last-first)/3;
  PIPE.stages=[0,1,2,3].map(i=>first+step*i);
  PIPE.stages.push((PIPE.boundaryX+right)/2);
}
function clamp(x,a,b){ return Math.max(a,Math.min(b,x)); }

function pipeEmit(){
  for(let k=0;k<16;k++) PIPE.parts.push({t:-k*0.055,sp:0.0058+Math.random()*0.0022,off:(Math.random()-.5)*18});
}
function drawScenePipeline(ctx,dt){
  if(PIPE.W!==STAGE.W||PIPE.H!==STAGE.H) pipeLayout();
  const {W,H}=PIPE, midY=H*0.56;

  // two territories, one membrane. The wash is barely there on purpose — it should register
  // as "these are different places" without ever competing with the material moving across.
  const bx=PIPE.boundaryX;
  ctx.fillStyle="rgba(255,169,92,.03)"; ctx.fillRect(0,0,bx,H);
  ctx.fillStyle="rgba(78,168,255,.035)"; ctx.fillRect(bx,0,W-bx,H);
  ctx.save();
  ctx.strokeStyle="rgba(78,168,255,.45)"; ctx.lineWidth=1.2; ctx.setLineDash([4,6]);
  ctx.beginPath(); ctx.moveTo(bx,midY-150); ctx.lineTo(bx,midY+120); ctx.stroke();
  ctx.restore();
  ctx.font="10px 'IBM Plex Mono',Consolas,monospace";
  ctx.textAlign="right"; ctx.fillStyle="#9A6636";
  ctx.fillText(t("p_here").toUpperCase().split("").join(" "),bx-15,midY-158);
  ctx.textAlign="left"; ctx.fillStyle="#3C6FA8";
  ctx.fillText(t("p_beyond").toUpperCase().split("").join(" "),bx+15,midY-158);

  // the local rail, then a separate crossing that only masked material uses
  ctx.strokeStyle="rgba(122,168,235,.16)"; ctx.lineWidth=1;
  ctx.beginPath(); ctx.moveTo(PIPE.stages[0],midY); ctx.lineTo(PIPE.stages[3],midY); ctx.stroke();
  ctx.strokeStyle="rgba(78,168,255,.3)";
  ctx.beginPath(); ctx.moveTo(PIPE.stages[3],midY); ctx.lineTo(PIPE.stages[4],midY); ctx.stroke();

  // stage markers
  const d=PIPE.data;
  // the masked stage deliberately repeats the leaf-count figure: masking does not change the
  // vector's length, only who can read it. Same numbers, different colour — that is the point.
  const cells=d.cells?d.cells.toLocaleString():"—";
  const vals=[String(d.samples||"—"),
              d.features?`${d.samples||"—"} × ${d.features}`:"—",
              cells, cells,
              d.bytes?humanBytes(d.bytes):"—"];
  PIPE.stages.forEach((x,i)=>{
    const tone=PIPE_TONE[i], col=PIPE_TINT[tone];
    ctx.beginPath(); ctx.arc(x,midY,7,0,Math.PI*2);
    ctx.fillStyle="#0A1424"; ctx.fill();
    ctx.strokeStyle=col; ctx.lineWidth=1.3; ctx.stroke();
    ctx.globalAlpha=.5; ctx.drawImage(PIPE_SPR[tone],x-24,midY-24,48,48); ctx.globalAlpha=1;
    ctx.textAlign="center";
    ctx.font="9px 'IBM Plex Mono',Consolas,monospace"; ctx.fillStyle="#9BB2D4";
    ctx.fillText(t(PIPE_KEYS[i]).toUpperCase().split("").join(" "),x,midY-34);
    ctx.font="600 16px 'IBM Plex Mono',Consolas,monospace"; ctx.fillStyle=col;
    ctx.fillText(vals[i],x,midY+38);
  });
  // travelling material: recolours as it passes each stage, and only azure crosses
  PIPE.parts=PIPE.parts.filter(p=>{
    p.t+=p.sp*(dt/0.016);
    if(p.t>=1) return false;
    if(p.t<0) return true;
    const seg=clamp(p.t,0,1)*4, i=Math.min(3,Math.floor(seg)), f=seg-i;
    const x=PIPE.stages[i]+(PIPE.stages[i+1]-PIPE.stages[i])*f;
    const y=midY+p.off*Math.sin(Math.PI*p.t)*0.5;
    const tone=PIPE_TONE[i];
    ctx.globalAlpha=0.85*Math.sin(Math.PI*clamp(p.t,0,1));
    ctx.drawImage(PIPE_SPR[tone],x-7,y-7,14,14);
    ctx.globalAlpha=1;
    return true;
  });
}
function pipeReset(samples,features){
  PIPE.parts=[]; PIPE.data={samples:samples||0,features:features||0,cells:0,bytes:0,round:0};
}

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
  pipeReset(sel.scan.n_samples, sel.scan.n_features);
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
    const rd=s.current_round||s.rounds_done||0;
    $("#rsRound").textContent=rd;
    const v=s.fed_primary; $("#rsFed").textContent=(typeof v==="number")?v.toFixed(3):"…";
    $("#rsEps").textContent=(s.global_eps??0);
    const bud=sel.sch?.epsilon_budget||10; $("#epsFill").style.width=Math.min(100,100*(s.global_eps||0)/bud)+"%";
    $("#stEps").textContent=`ε ${s.global_eps??0} / ${bud}`;
    renderTraffic(s);
    PIPE.data.samples=s.n_samples||PIPE.data.samples;
    // feature width comes from the local folder scan; masked_cells is an optional display-only
    // field on the node summary. If a build does not report it the stage just reads "—".
    PIPE.data.cells=s.masked_cells||PIPE.data.cells;
    PIPE.data.bytes=s.application_bytes_sent||0;
    if(rd>PIPE.data.round){ PIPE.data.round=rd; pipeEmit(); }   // one burst per completed round
  }
  if(st.done){
    clearInterval(pollTimer); pollTimer=null;
    $("#stop").classList.add("hidden"); $("#restart").classList.remove("hidden");
    setConn(st.error?"on":"done");
    if(st.error) msg("#s4msg","bad",st.error);
    else msg("#s4msg","ok","✓ "+t("train_done"));
  }
}
$("#stop").onclick=async()=>{ $("#stop").disabled=true; await api().stop(); };
$("#restart").onclick=()=>{ setConn("on"); goStep(3); };

async function init(){
  try{ MODS=await api().list_modalities(); }catch(e){ MODS=[]; }
  try{ const d=await api().defaults();
    if(d){ $("#coord").value=d.coord||""; $("#nodeid").value=d.node_id||"node_1"; } }catch(e){}
  stageStart();
  applyLang();
  goStep(1);
}
window.addEventListener("pywebviewready", init);
// fallback if opened in a plain browser (no pywebview): still render UI
setTimeout(()=>{ if(!MODS.length && window.pywebview) init(); }, 300);
