/* Optional add-on: per-file accounting for browser video extraction.
 *
 * Purely additive and self-contained — its own DOM, CSS and strings. It only listens to the
 * "gbadf:video" CustomEvents that client.js emits; nothing in the extraction, feature or
 * federation path depends on it. Delete this file and the <script> tag in client.html and the
 * client behaves exactly as before.
 *
 * Shows, per selected video: class, source size -> kept NPZ size, resolution/duration, sampled
 * frames, and how many of those frames actually contained a detectable pose. Cumulative across
 * batches, so an ASD batch plus a TD batch add up to the folder this node will contribute.
 */
(() => {
  const HOST_SELECTOR = "#videoImport";
  // Above the preview panes: the bottom of the console stage is already occupied by the scene
  // caption, which is painted over the video import.
  const ANCHOR_SELECTOR = ".panes";
  const MIN_CDP_FRAMES = 24;                      // cdp_features.MIN_CDP_FRAMES
  const WEAK_POSE_RATE = 60;                      // below this, the clip is probably unusable

  const STRINGS = {
    en:{file:"File",cls:"Class",size:"Source → kept",clip:"Clip",sampled:"Sampled",pose:"Pose",
      state:"Status",queued:"queued",running:"extracting",saved:"saved",failed:"failed",
      cancelled:"cancelled",videos:"videos",source:"source",kept:"kept",frames:"sampled frames",
      points:"points",thin:`under ${MIN_CDP_FRAMES} frames — the CDP adapter will reject this clip`,
      weak:"few frames contained a detectable pose"},
    zh:{file:"文件",cls:"类别",size:"原始 → 保留",clip:"画面",sampled:"采样",pose:"识别率",
      state:"状态",queued:"待处理",running:"提取中",saved:"已保存",failed:"失败",
      cancelled:"已取消",videos:"个视频",source:"原始",kept:"保留",frames:"采样帧",
      points:"关键点",thin:`不足 ${MIN_CDP_FRAMES} 帧 — CDP 适配器会拒收该片段`,
      weak:"能识别出骨架的帧太少"},
    "zh-Hant":{file:"檔案",cls:"類別",size:"原始 → 保留",clip:"畫面",sampled:"取樣",pose:"辨識率",
      state:"狀態",queued:"待處理",running:"提取中",saved:"已儲存",failed:"失敗",
      cancelled:"已取消",videos:"個影片",source:"原始",kept:"保留",frames:"取樣影格",
      points:"關鍵點",thin:`不足 ${MIN_CDP_FRAMES} 影格 — CDP 轉接器會拒收該片段`,
      weak:"能辨識出骨架的影格太少"}
  };
  const CSS = `
.vfl{margin-top:10px;border:1px solid var(--line,#d8dfdf);border-radius:9px;overflow:hidden;
  background:var(--panel,#fff)}
.vfl.hidden{display:none}
.vfl-totals{padding:7px 11px;border-bottom:1px solid var(--line,#d8dfdf);background:rgba(0,0,0,.03);
  font-family:var(--mono,monospace);font-size:11px;color:var(--ink,#222)}
.vfl-head,.vfl-row{display:grid;
  grid-template-columns:24px minmax(84px,1.6fr) 44px 1.15fr 1.1fr .95fr 46px 62px;
  gap:8px;align-items:center;padding:5px 11px;font-family:var(--mono,monospace);font-size:10.5px}
.vfl-head{color:var(--mut,#6b7a78);text-transform:uppercase;letter-spacing:.4px;
  border-bottom:1px solid var(--line,#d8dfdf)}
.vfl-rows{max-height:128px;overflow:auto}
.vfl-row{border-top:1px solid rgba(0,0,0,.04);color:var(--ink,#222)}
.vfl-row>span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.vfl-idx,.vfl-state{color:var(--mut,#6b7a78)}
.vfl-tag{padding:1px 5px;border-radius:4px;text-align:center;font-size:9.5px;letter-spacing:.4px}
.vfl-tag.asd{background:rgba(226,141,117,.16);color:#a2503a}
.vfl-tag.td{background:rgba(106,174,224,.16);color:#2d6088}
.vfl-row.saved .vfl-state{color:var(--ok,#2f8f6b)}
.vfl-row.running .vfl-state{color:var(--blue,#3b7bbf)}
.vfl-row.failed .vfl-state,.vfl-warn{color:var(--bad,#c0503a)}

/* the preview panes hang their own labels above themselves, so leave room for those */
html[data-theme="console"] .vfl{margin:0 0 30px;border-color:rgba(122,168,235,.2);
  border-radius:0;background:rgba(6,14,26,.72)}
html[data-theme="console"] .vfl-totals{padding:6px 10px;border-bottom-color:rgba(122,168,235,.16);
  background:transparent;color:#a3b9d8;font:9.5px var(--mono);letter-spacing:.1em;
  text-transform:uppercase}
html[data-theme="console"] .vfl-head,html[data-theme="console"] .vfl-row{padding:4px 10px;
  font:9.5px var(--mono);letter-spacing:.05em}
html[data-theme="console"] .vfl-head{color:#3c6fa8;letter-spacing:.14em;
  border-bottom-color:rgba(122,168,235,.16)}
html[data-theme="console"] .vfl-rows{max-height:100px}
html[data-theme="console"] .vfl-row{border-top-color:rgba(122,168,235,.07);color:#a3b9d8}
html[data-theme="console"] .vfl-idx,html[data-theme="console"] .vfl-state{color:#66809f}
html[data-theme="console"] .vfl-tag{border-radius:0;background:transparent;border:1px solid}
html[data-theme="console"] .vfl-tag.asd{color:#ffa95c;border-color:rgba(255,169,92,.35)}
html[data-theme="console"] .vfl-tag.td{color:#4ea8ff;border-color:rgba(78,168,255,.35)}
html[data-theme="console"] .vfl-row.saved .vfl-state{color:#4ea8ff}
html[data-theme="console"] .vfl-row.running .vfl-state{color:#eaf2ff}
html[data-theme="console"] .vfl-row.failed .vfl-state,html[data-theme="console"] .vfl-warn{
  color:#e2705f}
`;

  const items = [];
  let box = null, totals = null, head = null, rows = null;

  const lang = () => {
    const value = document.documentElement.lang || "en";
    return STRINGS[value] ? value : "en";
  };
  const s = key => STRINGS[lang()][key];
  const escape = text => String(text).replace(/[&<>"]/g,
    ch => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"}[ch]));
  const bytes = n => n < 1024 ? `${n} B`
    : n < 1048576 ? `${(n / 1024).toFixed(0)} KB` : `${(n / 1048576).toFixed(1)} MB`;
  const isCdp = () => (typeof sel !== "undefined" && sel?.modality) === "action_cdp";

  function mount(){
    if(box) return true;
    const host = document.querySelector(HOST_SELECTOR);
    const anchor = document.querySelector(ANCHOR_SELECTOR);
    if(!host || !anchor) return false;
    const style = document.createElement("style");
    style.textContent = CSS;
    document.head.appendChild(style);
    box = document.createElement("div");
    box.className = "vfl hidden";
    totals = document.createElement("div");
    totals.className = "vfl-totals";
    head = document.createElement("div");
    head.className = "vfl-head";
    rows = document.createElement("div");
    rows.className = "vfl-rows";
    box.append(totals, head, rows);
    host.insertBefore(box, anchor);
    // client.js sets documentElement.lang whenever the language changes
    new MutationObserver(render).observe(document.documentElement,
      {attributes:true, attributeFilter:["lang"]});
    return true;
  }
  function itemFor(file){
    return items.find(entry => entry.file === file) || null;
  }
  function render(){
    if(!mount()) return;
    box.classList.toggle("hidden", !items.length);
    if(!items.length){ rows.innerHTML = ""; totals.textContent = ""; head.innerHTML = ""; return; }
    head.innerHTML = ["#", s("file"), s("cls"), s("size"), s("clip"), s("sampled"), s("pose"),
      s("state")].map((text, index) =>
        `<span${index ? "" : ' class="vfl-idx"'}>${escape(text)}</span>`).join("");
    const cdp = isCdp();
    rows.innerHTML = items.map((item, index) => {
      const rate = item.frames ? Math.round(100 * item.detected / item.frames) : null;
      const kept = item.bytes ? ` → ${bytes(item.bytes)}` : "";
      const clip = item.width ? `${item.width}×${item.height} · ${(item.duration || 0).toFixed(1)}s`
        : "—";
      const sampled = item.frames ? `${item.frames} f · ${item.fps || "?"} fps` : "—";
      const thin = cdp && item.frames > 0 && item.frames < MIN_CDP_FRAMES;
      const weak = rate != null && item.state === "saved" && rate < WEAK_POSE_RATE;
      const note = item.error || (thin ? s("thin") : weak ? s("weak") : item.path || item.name);
      return `<div class="vfl-row ${item.state}" title="${escape(note)}">` +
        `<span class="vfl-idx">${String(index + 1).padStart(2, "0")}</span>` +
        `<span>${escape(item.name)}</span>` +
        `<span class="vfl-tag ${item.label.toLowerCase()}">${escape(item.label)}</span>` +
        `<span>${bytes(item.size)}${kept}</span>` +
        `<span>${clip}</span>` +
        `<span class="${thin ? "vfl-warn" : ""}">${sampled}${thin ? " ⚠" : ""}</span>` +
        `<span class="${weak ? "vfl-warn" : ""}">${rate == null ? "—" : `${rate}%`}</span>` +
        `<span class="vfl-state">${escape(s(item.state))}</span></div>`;
    }).join("");
    const done = items.filter(item => item.state === "saved");
    const asd = items.filter(item => item.label === "ASD").length;
    const sourceBytes = items.reduce((sum, item) => sum + item.size, 0);
    const keptBytes = done.reduce((sum, item) => sum + (item.bytes || 0), 0);
    const frames = done.reduce((sum, item) => sum + (item.frames || 0), 0);
    const points = done.find(item => item.points)?.points || 33;
    totals.textContent =
      `${items.length} ${s("videos")} · ASD ${asd} / TD ${items.length - asd} · ` +
      `${s("source")} ${bytes(sourceBytes)} → ${s("kept")} ${bytes(keptBytes)} · ` +
      `${frames} ${s("frames")} × ${points} ${s("points")}`;
  }

  document.addEventListener("gbadf:video", event => {
    const {phase, file} = event.detail || {};
    if(phase === "batch"){
      (event.detail.files || []).forEach(entry => {
        if(itemFor(entry)) return;
        items.push({file:entry, name:entry.name, size:entry.size,
          label:event.detail.label || "ASD", state:"queued", fps:null, frames:0, detected:0,
          duration:null, width:0, height:0, bytes:0, points:0, path:null, error:null});
      });
    }else{
      const item = itemFor(file);
      if(!item) return;
      if(phase === "start") Object.assign(item, {state:"running", fps:event.detail.fps,
        frames:event.detail.count, detected:0, duration:event.detail.duration,
        width:event.detail.width, height:event.detail.height});
      else if(phase === "frame") item.detected = event.detail.detected;
      else if(phase === "saved") Object.assign(item, {state:"saved",
        path:event.detail.result?.path || null, bytes:event.detail.result?.bytes || 0,
        points:event.detail.result?.points || 33, frames:event.detail.frames || item.frames});
      else if(phase === "failed") Object.assign(item, {state:"failed", error:event.detail.error});
      else if(phase === "cancelled") item.state = "cancelled";
    }
    render();
  });
})();
