/* Live, privacy-safe federation progress for the desktop training step. */
(() => {
  const STRINGS = {
    en: {starting:"Connecting to the coordinator", registered:"Registered — waiting for the cohort",
      waiting_for_cohort:"Waiting for the cohort", cohort_ready:"Cohort complete — starting",
      counting:"Counting local rows into the shared trees",
      submitted:"Count payload sent — waiting for the other institutions",
      aggregated:"Round aggregated", done:"Complete", stopped:"Stopped",
      round:"Round", of:"of", waiting_note:"aggregation starts only after every institution submits"},
    zh: {starting:"正在连接协调器", registered:"已注册 — 等待其他机构",
      waiting_for_cohort:"等待其他机构", cohort_ready:"机构已齐 — 即将开始",
      counting:"正在将本地数据计入共享树", submitted:"计数载荷已发送 — 等待其他机构",
      aggregated:"本轮已聚合", done:"已完成", stopped:"已停止",
      round:"第", of:"轮 / 共", waiting_note:"所有机构提交后才会开始聚合"},
    "zh-Hant": {starting:"正在連線協調器", registered:"已註冊 — 等待其他機構",
      waiting_for_cohort:"等待其他機構", cohort_ready:"機構已齊 — 即將開始",
      counting:"正在將本地資料計入共享樹", submitted:"計數載荷已送出 — 等待其他機構",
      aggregated:"本輪已聚合", done:"已完成", stopped:"已停止",
      round:"第", of:"輪 / 共", waiting_note:"所有機構提交後才會開始聚合"}
  };
  const CSS = `
.rp{margin:0 0 14px;max-width:720px}.rp.hidden{display:none}
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
.rp-cohort{margin-top:5px;font-family:var(--mono,monospace);font-size:10px;color:var(--mut,#6b7a78)}
.rp-dots{display:inline-flex;gap:4px;margin-left:6px;vertical-align:middle}
.rp-dots i{width:6px;height:6px;border-radius:50%;background:currentColor;opacity:.25}
.rp-dots i.on{opacity:1}@keyframes rpwait{0%{transform:translateX(-100%)}100%{transform:translateX(100%)}}
html[data-theme="console"] .rp{max-width:none;margin:38px 0 18px}
html[data-theme="console"] .rp-top{font:9.5px var(--mono);letter-spacing:.12em;text-transform:uppercase;color:#66809f}
html[data-theme="console"] .rp-count{color:#eaf2ff}
html[data-theme="console"] .rp-track{height:2px;border-radius:0;background:rgba(255,255,255,.07)}
html[data-theme="console"] .rp-fill{border-radius:0;background:var(--accent);box-shadow:0 0 10px rgba(78,168,255,.6)}
html[data-theme="console"] .rp-cohort{font:9px var(--mono);letter-spacing:.1em;text-transform:uppercase;color:#66809f}`;
  const PENDING = new Set(["registered", "waiting_for_cohort", "submitted"]);
  let box, phaseEl, countEl, fill, cohortEl, last;

  const language = () => STRINGS[document.documentElement.lang] ? document.documentElement.lang : "en";
  const string = key => STRINGS[language()][key] || key;

  function mount() {
    if (box) return true;
    const host = document.querySelector('[data-step="4"]');
    const anchor = host?.querySelector(".runstats");
    if (!host || !anchor) return false;
    const style = document.createElement("style");
    style.textContent = CSS;
    document.head.appendChild(style);
    box = document.createElement("div");
    box.className = "rp hidden";
    box.innerHTML = '<div class="rp-top"><span class="rp-phase"></span><span class="rp-count"></span></div>' +
      '<div class="rp-track"><div class="rp-fill"></div></div><div class="rp-cohort"></div>';
    host.insertBefore(box, anchor);
    phaseEl = box.querySelector(".rp-phase");
    countEl = box.querySelector(".rp-count");
    fill = box.querySelector(".rp-fill");
    cohortEl = box.querySelector(".rp-cohort");
    return true;
  }

  function render(state, summary) {
    if (!mount()) return;
    if (!state || (!summary && !state.running)) { box.classList.add("hidden"); return; }
    box.classList.remove("hidden");
    const done = Number(summary?.rounds_done || 0);
    const total = Number(summary?.rounds_total || document.querySelector("#rounds")?.value || 5);
    const phase = state.done ? (state.error ? "stopped" : "done") : (summary?.phase || "starting");
    const pending = !state.done && PENDING.has(phase);
    phaseEl.textContent = string(phase);
    countEl.textContent = `${string("round")} ${Math.min(done + (state.done ? 0 : 1), total)} ${string("of")} ${total}`;
    fill.classList.toggle("pending", pending);
    fill.style.width = pending && !done ? "100%" : `${Math.round(100 * done / Math.max(1, total))}%`;
    const size = Number(summary?.cohort_size || 0);
    if (size > 1 && !state.done) {
      const active = new Set(["cohort_ready", "counting", "submitted", "aggregated"]);
      const seen = Math.max(Number(summary?.cohort_seen || 0), active.has(phase) ? size : 0);
      const dots = Array.from({length:size}, (_value, i) => `<i class="${i < seen ? "on" : ""}"></i>`).join("");
      cohortEl.innerHTML = `${seen}/${size}<span class="rp-dots">${dots}</span>` +
        (phase === "submitted" ? ` · ${string("waiting_note")}` : "");
    } else cohortEl.textContent = "";
  }

  document.addEventListener("gbadf:run", event => {
    last = event.detail || null;
    render(last?.state, last?.summary);
  });
  new MutationObserver(() => { if (last) render(last.state, last.summary); })
    .observe(document.documentElement, {attributes:true, attributeFilter:["lang"]});
})();
