/* Optional add-on: one-click import of the screened rehearsal clips.
 *
 * Purely additive and self-contained — its own DOM, CSS and strings. It builds ordinary File
 * objects and hands them to the same runVideoBatch() path that the "Extract raw video…" file
 * dialog already uses, so extraction, saving, scanning and the federation path are untouched.
 * Delete this file and the <script> tag in client.html and the client behaves exactly as before.
 *
 * It exists because on stage the operator otherwise has to hand-pick clips out of a native file
 * dialog in front of an audience — slow, and easy to pick the wrong node's clips. The bytes come
 * from Api.demo_clip() in client_app.py: pywebview serves this page out of static/, so
 * JavaScript cannot reach demo_videos/ over its own origin.
 *
 * On a machine without a demo_videos/ folder (a partner running the client on their own data)
 * demo_clip() reports nothing on disk and this add-on never mounts.
 */
(() => {
  /* ===== EDIT ME ============================================================================
   * The rehearsal batches, keyed by node number: node_1 runs batch 1, and so on. Names are
   * files inside demo_videos/<class>/. Everything the UI shows — the buttons, their labels,
   * the clip counts, which clips get which class — is derived from this one object, and it is
   * also the only list of clips this add-on will load, so changing a batch means editing only
   * the lines below.
   *
   * Why these six and not all eleven clips in demo_videos/. A clip-quality audit found that
   * td_02, td_04 and td_05 film children whose legs are out of shot, and MediaPipe answers by
   * extrapolating confident lower-body landmarks outside the camera frame (46.7% / 31.7% /
   * 46.9% of drawn lower-body landmark-slots, against 0.0–0.9% for every other clip). Projected
   * on stage that reads as the system inventing data, so they must never be loaded here.
   * asd_06 is clean but runs 38.7 s, about three times the next longest clip, and would stall
   * the live extraction. That leaves asd_01..asd_05 plus td_01 and td_03 as presentable, and
   * only two clean TD clips for three batches — so batch 3 is deliberately single-class. One
   * institution contributing a single cohort is realistic, and the class balance behind the
   * displayed metric comes from the synthetic baseline cohort, not from these rows.
   * ========================================================================================= */
  const BATCHES = {
    1: {asd: ["asd_01.mp4"], td: ["td_01.mp4"]},
    2: {asd: ["asd_03.mp4"], td: ["td_03.mp4"]},
    3: {asd: ["asd_02.mp4", "asd_04.mp4"]}
  };

  const HOST_SELECTOR = "#videoImport";
  // The console theme right-aligns the class/sample-rate selects and hides the panel title, so
  // the left half of that row is empty and is where these buttons belong. Living inside
  // #videoImport also means they appear and disappear with the action modalities for free.
  const ANCHOR_SELECTOR = ".videohead";

  const STRINGS = {
    en:{title:"Rehearsal clips", batch:"Batch", suggested:"this node",
      missing:"clips missing", loading:"reading", busy:"extraction running"},
    zh:{title:"彩排片段", batch:"批次", suggested:"本节点",
      missing:"缺少片段", loading:"正在读取", busy:"正在提取"},
    "zh-Hant":{title:"彩排片段", batch:"批次", suggested:"本節點",
      missing:"缺少片段", loading:"正在讀取", busy:"正在提取"}
  };
  const CSS = `
.gbb{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-right:auto}
.gbb-label{color:var(--mut,#6b7a78);font-family:var(--mono,monospace);font-size:10.5px;
  letter-spacing:.06em;margin-right:2px}
.gbb-btn{display:flex;flex-direction:column;gap:2px;padding:5px 11px;cursor:pointer;
  border:1px solid var(--line,#d8dfdf);border-radius:8px;background:var(--panel,#fff);
  color:var(--ink,#222);font-family:var(--mono,monospace);line-height:1.25;text-align:left}
.gbb-btn b{font-size:11px;font-weight:600}
.gbb-btn span{font-size:9.5px;color:var(--mut,#6b7a78)}
.gbb-btn:hover:not(:disabled){border-color:var(--blue,#3b7bbf)}
.gbb-btn:disabled{opacity:.4;cursor:default}
.gbb-btn.on{border-color:var(--blue,#3b7bbf);background:rgba(59,123,191,.08)}
.gbb-status{color:var(--mut,#6b7a78);font-family:var(--mono,monospace);font-size:10px}
.gbb-status.bad{color:var(--bad,#c0503a)}

html[data-theme="console"] .gbb-label{color:#3c6fa8;font:9px var(--mono);letter-spacing:.2em;
  text-transform:uppercase}
html[data-theme="console"] .gbb-btn{padding:5px 12px;border-radius:0;
  border-color:rgba(122,168,235,.24);background:transparent;color:#a3b9d8}
html[data-theme="console"] .gbb-btn b{font:10px var(--mono);letter-spacing:.14em;
  text-transform:uppercase}
html[data-theme="console"] .gbb-btn span{font:8.5px var(--mono);letter-spacing:.12em;color:#66809f}
html[data-theme="console"] .gbb-btn:hover:not(:disabled){border-color:var(--accent);
  color:var(--accent)}
html[data-theme="console"] .gbb-btn.on{border-color:var(--accent);background:rgba(78,168,255,.07);
  color:var(--accent);box-shadow:0 0 14px rgba(78,168,255,.1)}
html[data-theme="console"] .gbb-btn.on b{color:var(--accent)}
html[data-theme="console"] .gbb-status{font:9px var(--mono);letter-spacing:.12em;
  text-transform:uppercase;color:#66809f}
html[data-theme="console"] .gbb-status.bad{color:#e2705f}
`;

  const available = new Set();                  // "asd/asd_01.mp4" entries that exist on disk
  let bar = null, suggested = 0, busy = false, status = "", statusBad = false;

  const lang = () => {
    const value = document.documentElement.lang || "en";
    return STRINGS[value] ? value : "en";
  };
  const s = key => STRINGS[lang()][key] || key;
  const api = () => window.pywebview.api;
  const clipsOf = spec => Object.entries(spec)
    .flatMap(([cls, names]) => names.map(name => `${cls}/${name}`));
  const decode = b64 => {
    const binary = atob(b64), out = new Uint8Array(binary.length);
    for(let i = 0; i < binary.length; i++) out[i] = binary.charCodeAt(i);
    return out;
  };
  // client.js owns the extraction lock; the buttons follow it so a manual pick and a batch
  // cannot both drive the video element.
  const extracting = () => busy ||
    (typeof videoImport !== "undefined" && videoImport.running);

  function setStatus(text, bad = false){ status = text; statusBad = bad; render(); }

  function mount(){
    if(bar) return true;
    const host = document.querySelector(HOST_SELECTOR);
    const anchor = host && host.querySelector(ANCHOR_SELECTOR);
    if(!host || !anchor) return false;
    const style = document.createElement("style");
    style.textContent = CSS;
    document.head.appendChild(style);
    bar = document.createElement("div");
    bar.className = "gbb";
    anchor.insertBefore(bar, anchor.firstChild);
    // client.js sets documentElement.lang whenever the language changes
    new MutationObserver(render).observe(document.documentElement,
      {attributes:true, attributeFilter:["lang"]});
    // #cancelVideo is shown exactly while an extraction holds the video element
    new MutationObserver(render).observe(document.querySelector("#cancelVideo"),
      {attributes:true, attributeFilter:["class"]});
    return true;
  }

  function render(){
    if(!mount()) return;
    const locked = extracting();
    bar.innerHTML = `<span class="gbb-label">${s("title")}</span>` +
      Object.keys(BATCHES).map(key => {
        const spec = BATCHES[key];
        const missing = clipsOf(spec).some(clip => !available.has(clip));
        const counts = Object.entries(spec)
          .map(([cls, names]) => `${names.length} ${cls.toUpperCase()}`).join(" · ");
        const on = Number(key) === suggested && !missing;
        return `<button type="button" class="gbb-btn${on ? " on" : ""}" data-batch="${key}"` +
          `${missing || locked ? " disabled" : ""}>` +
          `<b>${s("batch")} ${key}</b>` +
          `<span>${missing ? s("missing") : counts}${on ? ` · ${s("suggested")}` : ""}</span>` +
          `</button>`;
      }).join("") +
      `<span class="gbb-status${statusBad ? " bad" : ""}">${status}</span>`;
    bar.querySelectorAll("[data-batch]").forEach(button => {
      button.onclick = () => run(button.dataset.batch);
    });
  }

  async function run(key){
    if(extracting()) return;
    busy = true; setStatus("");
    try{
      const dest = await api().video_output();
      if(!dest?.ok){ setStatus(dest?.error || "no output folder", true); return; }
      // Read every clip first: a missing file should stop the batch before the audience sees
      // half an extraction, not midway through it.
      const groups = [];
      for(const [cls, names] of Object.entries(BATCHES[key])){
        const files = [];
        for(const name of names){
          setStatus(`${s("loading")} ${name}`);
          const clip = await api().demo_clip(`${cls}/${name}`);
          if(!clip?.ok){ setStatus(clip?.error || `cannot read ${name}`, true); return; }
          files.push(new File([decode(clip.data)], name, {type:"video/mp4"}));
        }
        if(files.length) groups.push({label:cls.toUpperCase(), files});
      }
      setStatus("");
      // Optional observers (client_nowplaying.js) use this to caption the whole batch as one
      // queue; client.js only ever sees one single-class batch at a time, below.
      document.dispatchEvent(new CustomEvent("gbadf:batch", {detail:{
        batch:Number(key), groups, files:groups.flatMap(group => group.files)}}));
      // One runVideoBatch per class, because the saved label is the panel's class selector —
      // this is the same "one class per batch" contract the file dialog already works under.
      for(const group of groups){
        document.querySelector("#videoLabel").value = group.label;
        await runVideoBatch(group.files, dest);
        // a cancel, or a MediaPipe failure that left a retry pending, ends the whole batch
        if(videoImport.cancelled || videoImport.pendingFiles) break;
      }
    }catch(error){
      setStatus(String(error?.message || error), true);
    }finally{
      busy = false; render();
    }
  }

  async function boot(){
    // Ask only about the clips the batches name — never for a folder listing — so a clip the
    // audit kept out of BATCHES cannot reach this UI even by being present on disk.
    const wanted = [...new Set(Object.values(BATCHES).flatMap(clipsOf))];
    try{
      for(const clip of wanted){
        if((await api().demo_clip(clip, false))?.ok) available.add(clip);
      }
    }catch(_e){ return; }
    if(!available.size) return;                        // no demo_videos/ here: stay invisible
    try{
      const defaults = await api().defaults();
      suggested = Number(/node_(\d+)$/.exec(defaults?.node_id || "")?.[1]) || 0;
    }catch(_e){}
    render();
  }
  window.addEventListener("pywebviewready", boot);
})();
