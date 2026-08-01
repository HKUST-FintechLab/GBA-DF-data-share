/* Optional add-on: a progress bar and a phase line for the live training step.
 *
 * Purely additive and self-contained — its own DOM, CSS and strings. It only listens to the
 * "gbadf:run" CustomEvent that client.js emits on every poll. Delete this file and the
 * <script> tag in client.html and the client behaves exactly as before.
 *
 * It exists because the round counter, epsilon and payload bytes all read zero until a whole
 * round has completed, which makes a run that is waiting on another institution look broken.
 * The phase line names what the node is actually doing, and the bar shows rounds completed.
 */
(() => {
  const HOST_SELECTOR = '[data-step="4"]';
  const ANCHOR_SELECTOR = ".runstats";            // the bar sits directly above the counters

  const STRINGS = {
    en:{starting:"connecting to the coordinator",registered:"registered — waiting for the cohort",
      waiting_for_cohort:"waiting for the cohort",cohort_ready:"cohort complete — starting",
      counting:"counting local rows into the shared trees",
      submitted:"masked counts sent — waiting for the other institutions",
      aggregated:"round aggregated",done:"complete",stopped:"stopped",
      round:"round",of:"of",waiting_note:"nothing is aggregated until every institution submits"},
    zh:{starting:"正在连接协调器",registered:"已注册 — 等待其它机构",
      waiting_for_cohort:"等待其它机构",cohort_ready:"机构已齐 — 即将开始",
      counting:"正在把本地数据计入共享树",
      submitted:"掩码计数已发送 — 等待其它机构",
      aggregated:"本轮已聚合",done:"已完成",stopped:"已停止",
      round:"第",of:"轮 / 共",waiting_note:"所有机构都提交前不会发生任何聚合"},
    "zh-Hant":{starting:"正在連線協調器",registered:"已註冊 — 等待其它機構",
      waiting_for_cohort:"等待其它機構",cohort_ready:"機構已齊 — 即將開始",
      counting:"正在把本地資料計入共享樹",
      submitted:"遮罩計數已送出 — 等待其它機構",
      aggregated:"本輪已聚合",done:"已完成",stopped:"已停止",
      round:"第",of:"輪 / 共",waiting_note:"所有機構都提交前不會發生任何聚合"}
  };
  const CSS = `
.rp{margin:0 0 14px;max-width:720px}
.rp.hidden{display:none}
.rp-top{display:flex;gap:12px;align-items:baseline;justify-content:space-between;
  font-family:var(--mono,monospace);font-size:11px;color:var(--mut,#6b7a78)}
.rp-phase{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.rp-count{color:var(--ink,#222);font-variant-numeric:tabular-nums;white-space:nowrap}
.rp-track{position:relative;height:6px;margin-top:6px;border-radius:4px;overflow:hidden;
  background:rgba(0,0,0,.08)}
.rp-fill{height:100%;width:0;border-radius:4px;background:var(--blue,#3b7bbf);
  transition:width .35s ease}
.rp-fill.pending{background:linear-gradient(90deg,transparent,var(--blue,#3b7bbf),transparent);
  animation:rpwait 1.25s ease-in-out infinite}
.rp-cohort{margin-top:5px;font-family:var(--mono,monospace);font-size:10px;
  color:var(--mut,#6b7a78)}
.rp-dots{display:inline-flex;gap:4px;margin-left:6px;vertical-align:middle}
.rp-dots i{width:6px;height:6px;border-radius:50%;background:currentColor;opacity:.25}
.rp-dots i.on{opacity:1}
@keyframes rpwait{0%{transform:translateX(-100%)}100%{transform:translateX(100%)}}

html[data-theme="console"] .rp{max-width:none;margin:38px 0 18px}
html[data-theme="console"] .rp-top{font:9.5px var(--mono);letter-spacing:.12em;
  text-transform:uppercase;color:#66809f}
html[data-theme="console"] .rp-count{color:#eaf2ff}
html[data-theme="console"] .rp-track{height:2px;border-radius:0;background:rgba(255,255,255,.07)}
html[data-theme="console"] .rp-fill{border-radius:0;background:var(--accent);
  box-shadow:0 0 10px rgba(78,168,255,.6)}
html[data-theme="console"] .rp-cohort{font:9px var(--mono);letter-spacing:.1em;
  text-transform:uppercase;color:#66809f}
`;
  // phases where the node has done its part and is blocked on someone else
  const PENDING = new Set(["registered", "waiting_for_cohort", "submitted"]);

  let box = null, phaseEl = null, countEl = null, fill = null, cohortEl = null;

  const lang = () => {
    const value = document.documentElement.lang || "en";
    return STRINGS[value] ? value : "en";
  };
  const s = key => STRINGS[lang()][key] || key;

  function mount(){
    if(box) return true;
    const host = document.querySelector(HOST_SELECTOR);
    const anchor = host && host.querySelector(ANCHOR_SELECTOR);
    if(!host || !anchor) return false;
    const style = document.createElement("style");
    style.textContent = CSS;
    document.head.appendChild(style);
    box = document.createElement("div");
    box.className = "rp hidden";
    box.innerHTML = '<div class="rp-top"><span class="rp-phase"></span>' +
      '<span class="rp-count"></span></div>' +
      '<div class="rp-track"><div class="rp-fill"></div></div>' +
      '<div class="rp-cohort"></div>';
    host.insertBefore(box, anchor);
    phaseEl = box.querySelector(".rp-phase");
    countEl = box.querySelector(".rp-count");
    fill = box.querySelector(".rp-fill");
    cohortEl = box.querySelector(".rp-cohort");
    return true;
  }

  function render(state, summary){
    if(!mount()) return;
    if(!state || (!summary && !state.running)){ box.classList.add("hidden"); return; }
    box.classList.remove("hidden");
    const done = summary?.rounds_done || 0;
    const total = summary?.rounds_total || Number(document.querySelector("#rounds")?.value) || 5;
    const phase = state.done ? (state.error ? "stopped" : "done") : (summary?.phase || "starting");
    const pending = !state.done && PENDING.has(phase);

    phaseEl.textContent = s(phase);
    // "round 2 of 5" / "第 2 轮 / 共 5"
    countEl.textContent =
      `${s("round")} ${Math.min(done + (state.done ? 0 : 1), total)} ${s("of")} ${total}`;
    fill.classList.toggle("pending", pending);
    // while blocked the bar shows the rounds already banked, not an invented fraction
    fill.style.width = pending && !done ? "100%" : `${Math.round(100 * done / total)}%`;

    const size = summary?.cohort_size || 0;
    if(size > 1 && !state.done){
      const seen = Math.max(summary?.cohort_seen || 0, phase === "counting" ||
        phase === "submitted" || phase === "aggregated" ? size : 0);
      const dots = Array.from({length:size},
        (_v, i) => `<i class="${i < seen ? "on" : ""}"></i>`).join("");
      cohortEl.innerHTML = `${seen}/${size}<span class="rp-dots">${dots}</span>` +
        (phase === "submitted" ? ` · ${s("waiting_note")}` : "");
    }else cohortEl.textContent = "";
  }

  let last = null;
  document.addEventListener("gbadf:run", event => {
    last = event.detail || null;
    render(last?.state, last?.summary);
  });
  // client.js sets documentElement.lang whenever the language changes
  new MutationObserver(() => { if(last) render(last.state, last.summary); })
    .observe(document.documentElement, {attributes:true, attributeFilter:["lang"]});
})();
