/* Names the video currently being decoded and shows its position in the local queue. */
(() => {
  const STRINGS = {
    en:{extracting:"extracting pose",saving:"saving NPZ",saved:"saved",failed:"failed",cancelled:"cancelled",queued:"queued"},
    zh:{extracting:"正在提取姿态",saving:"正在保存 NPZ",saved:"已保存",failed:"失败",cancelled:"已取消",queued:"待处理"},
    "zh-Hant":{extracting:"正在提取姿態",saving:"正在儲存 NPZ",saved:"已儲存",failed:"失敗",cancelled:"已取消",queued:"待處理"}
  };
  const CSS = `
.nwp{position:absolute;left:0;right:0;top:0;z-index:1;padding:9px 12px 22px;pointer-events:none;
  font-family:var(--mono,monospace);background:linear-gradient(180deg,rgba(6,14,26,.82),transparent)}
.nwp.hidden{display:none}.nwp-top,.nwp-bottom{display:flex;gap:10px;align-items:baseline;justify-content:space-between}
.nwp-name{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#eaf2ff;font-size:12px}
.nwp-pos{color:#eaf2ff;font-size:11px;font-variant-numeric:tabular-nums;white-space:nowrap}
.nwp-track{height:3px;margin-top:6px;border-radius:2px;overflow:hidden;background:rgba(255,255,255,.16)}
.nwp-fill{height:100%;width:0;border-radius:2px;background:#4ea8ff;transition:width .18s linear}
.nwp-bottom{align-items:center;margin-top:6px}.nwp-queue{display:flex;gap:4px;min-width:0;flex-wrap:wrap}
.nwp-queue i{width:13px;height:3px;border-radius:2px;background:rgba(255,255,255,.2)}
.nwp-queue i.done{background:rgba(78,168,255,.65)}.nwp-queue i.now{background:#eaf2ff}.nwp-queue i.failed{background:#e2705f}
.nwp-state{color:#a3b9d8;font-size:10px;white-space:nowrap}.nwp-state.failed{color:#e2705f}
html[data-theme="console"] .nwp{padding:26px 13px 11px}
html[data-theme="console"] .nwp-name{font:11px var(--mono);letter-spacing:.16em;text-transform:uppercase}
html[data-theme="console"] .nwp-pos{font:11px var(--mono);letter-spacing:.1em}
html[data-theme="console"] .nwp-track{height:2px;border-radius:0}
html[data-theme="console"] .nwp-fill{border-radius:0;background:var(--accent);box-shadow:0 0 10px rgba(78,168,255,.6)}
html[data-theme="console"] .nwp-queue i{border-radius:0}
html[data-theme="console"] .nwp-state{font:9px var(--mono);letter-spacing:.16em;text-transform:uppercase}`;
  let box,nameEl,posEl,fill,queueEl,stateEl;
  let queue=[],current=null,index=0,count=0;
  const lang = () => STRINGS[document.documentElement.lang] ? document.documentElement.lang : "en";
  const string = key => STRINGS[lang()][key] || key;
  const stem = name => String(name).replace(/\.[^.]+$/,"");
  const entry = file => queue.find(item => item.file === file) || null;

  function mount() {
    if (box) return true;
    const host = document.querySelector("#videoImport .preview:not(.kept)");
    if (!host) return false;
    const style=document.createElement("style"); style.textContent=CSS; document.head.appendChild(style);
    box=document.createElement("div"); box.className="nwp hidden";
    box.innerHTML='<div class="nwp-top"><span class="nwp-name"></span><span class="nwp-pos"></span></div>' +
      '<div class="nwp-track"><div class="nwp-fill"></div></div>' +
      '<div class="nwp-bottom"><span class="nwp-queue"></span><span class="nwp-state"></span></div>';
    host.appendChild(box); nameEl=box.querySelector(".nwp-name"); posEl=box.querySelector(".nwp-pos");
    fill=box.querySelector(".nwp-fill"); queueEl=box.querySelector(".nwp-queue"); stateEl=box.querySelector(".nwp-state");
    new MutationObserver(render).observe(document.documentElement,{attributes:true,attributeFilter:["lang"]});
    return true;
  }
  function render() {
    if (!mount()) return;
    box.classList.toggle("hidden",!queue.length); if (!queue.length) return;
    const shown=current || queue.find(item => item.state === "queued") || queue[queue.length-1];
    nameEl.textContent=stem(shown.name); posEl.textContent=`${queue.indexOf(shown)+1} / ${queue.length}`;
    fill.style.width=current && count ? `${Math.round(100*index/count)}%` : shown.state === "saved" ? "100%" : "0";
    queueEl.innerHTML=queue.map(item => `<i class="${item === shown && current ? "now" : item.state === "saved" ? "done" : item.state === "failed" ? "failed" : ""}"></i>`).join("");
    stateEl.className=`nwp-state${shown.state === "failed" ? " failed" : ""}`;
    stateEl.textContent=shown.error || string(current ? (count && index >= count ? "saving" : "extracting") : shown.state);
  }
  function reset(files) { queue=files.map(file => ({file,name:file.name,state:"queued",error:null})); current=null; index=0; count=0; render(); }
  document.addEventListener("gbadf:video", event => {
    const {phase,file}=event.detail || {};
    if (phase === "batch") { const files=event.detail.files || []; if (!files.every(item => entry(item))) reset(files); return; }
    if (phase === "batch_finished" && event.detail.cancelled) {
      queue.forEach(item => { if (item.state === "queued") item.state="cancelled"; }); render(); return;
    }
    const item=entry(file); if (!item) return;
    if (phase === "start") { current=item; item.state="running"; index=0; count=event.detail.count || 0; }
    else if (phase === "frame") index=event.detail.index || index;
    else if (phase === "saved") { item.state="saved"; current=null; }
    else if (phase === "failed") { item.state="failed"; item.error=event.detail.error; current=null; }
    else if (phase === "cancelled") { item.state="cancelled"; current=null; }
    render();
  });
})();
