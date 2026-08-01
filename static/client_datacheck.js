/* Optional add-on: a data health check on the folder this node is about to contribute.
 *
 * Purely additive and self-contained — its own DOM, CSS and strings. It only listens to the
 * "gbadf:scan" CustomEvent that client.js emits after a folder scan. Delete this file and the
 * <script> tag in client.html and the client behaves exactly as before.
 *
 * It never blocks the run. A live demo should not be stopped by a warning, and a partner may
 * have a good reason to contribute a small batch. It only makes the consequence visible BEFORE
 * training rather than after: the coordinator adds Laplace noise to every leaf-count cell, so a
 * handful of rows produces a model whose score ordering is essentially noise, and a folder with
 * one class present cannot teach the forest to separate the two.
 */
(() => {
  const HOST_SELECTOR = '[data-step="2"]';
  const ANCHOR_SELECTOR = "#s2msg";                 // sits with the other step-2 messages
  const THIN_ROWS = 20;                             // below this, DP noise dominates
  const LEAN_ROWS = 60;                             // below this, expect a weak, jumpy curve

  const STRINGS = {
    en:{
      one_class:"Only one class in this folder",
      one_class_why:"Fine as long as another institution in the cohort holds the other class: the " +
        "coordinator sums everyone's leaf counts, so the pooled table is the same as if the data " +
        "had been pooled, and single-class sites cost nothing. It only fails if NO node contributes " +
        "the missing class. This client cannot see the other nodes' labels — class counts are " +
        "deliberately never uploaded — so confirm coverage with your cohort.",
      thin:"Very few training rows",
      thin_why:"The coordinator adds Laplace noise to every leaf-count cell. With this few rows the " +
        "noise dominates the counts and the resulting AUC is close to a coin flip — the run will " +
        "complete and the audit chain will be valid, but the metric will not mean anything.",
      lean:"Small batch",
      lean_why:"Enough to train, but expect a modest and jumpy metric. More recordings per class " +
        "give the privacy noise less room.",
      ok:"Batch looks usable",
      ok_why:"Both classes present with enough rows for the metric to carry signal.",
      rows:"rows", per:"per class", note:"This is a local check. Nothing here is sent anywhere."
    },
    zh:{
      one_class:"这个文件夹只有一个类别",
      one_class_why:"只要 cohort 里有别的机构持有另一类，这没有问题：协调器把所有机构的叶计数" +
        "相加，池化后的表和把数据汇总起来数出来的完全一样，单类别机构不带来任何损失。" +
        "只有当整个 cohort 都没有另一类时才会失效。本客户端看不到其它节点的标签" +
        "（类别计数从不上传），请与 cohort 内确认覆盖情况。",
      thin:"训练样本过少",
      thin_why:"协调器会给每一个叶计数格子加 Laplace 噪声。样本这么少时噪声会盖过计数，" +
        "得到的 AUC 接近抛硬币——训练能跑完、审计链也有效，但这个指标没有意义。",
      lean:"批次偏小",
      lean_why:"够训练，但指标会偏低且波动。每类多一些录制，隐私噪声的影响就小一些。",
      ok:"批次可用",
      ok_why:"两个类别都有，行数足以让指标带上信号。",
      rows:"行", per:"每类", note:"这是本地检查，任何内容都不会外传。"
    },
    "zh-Hant":{
      one_class:"這個資料夾只有一個類別",
      one_class_why:"只要 cohort 裡有其它機構持有另一類，這沒有問題：協調器把所有機構的葉計數" +
        "相加，池化後的表和把資料彙總起來數出來的完全一樣，單類別機構不帶來任何損失。" +
        "只有當整個 cohort 都沒有另一類時才會失效。本客戶端看不到其它節點的標籤" +
        "（類別計數從不上傳），請與 cohort 內確認覆蓋情況。",
      thin:"訓練樣本過少",
      thin_why:"協調器會為每一個葉計數格子加 Laplace 雜訊。樣本這麼少時雜訊會蓋過計數，" +
        "得到的 AUC 接近擲硬幣——訓練能跑完、稽核鏈也有效，但這個指標沒有意義。",
      lean:"批次偏小",
      lean_why:"夠訓練，但指標會偏低且波動。每類多一些錄製，隱私雜訊的影響就小一些。",
      ok:"批次可用",
      ok_why:"兩個類別都有，列數足以讓指標帶上訊號。",
      rows:"列", per:"每類", note:"這是本機檢查，任何內容都不會外傳。"
    }
  };
  const CSS = `
.dchk{margin:10px 0 0;padding:10px 12px;border-left:2px solid;border-radius:6px;
  font-family:var(--mono,monospace);font-size:11px;line-height:1.65}
.dchk.hidden{display:none}
.dchk-title{font-weight:700;margin-bottom:3px}
.dchk-why{opacity:.85}
.dchk-nums{margin-top:5px;opacity:.7}
.dchk.bad{border-color:var(--bad,#c0503a);color:var(--bad,#c0503a);background:rgba(192,80,58,.06)}
.dchk.warn{border-color:var(--warn,#b8860b);color:var(--warn,#b8860b);background:rgba(184,134,11,.06)}
.dchk.ok{border-color:var(--ok,#2f8f6b);color:var(--ok,#2f8f6b);background:rgba(47,143,107,.06)}

/* The console stage puts step 2 behind a fixed video-import overlay and keeps the scene caption
   in the bottom-left corner, so an in-flow message would be hidden underneath both. Park this in
   the free bottom-right column, above the navigation. */
html[data-theme="console"] .dchk{position:fixed;right:34px;bottom:96px;z-index:8;
  width:min(430px,39vw);border-radius:0;padding:9px 11px;font:10px/1.7 var(--mono);
  background:rgba(6,14,26,.94)}
html[data-theme="console"] .dchk.bad{color:#e2705f;border-color:#e2705f}
html[data-theme="console"] .dchk.warn{color:#d9a441;border-color:#d9a441}
html[data-theme="console"] .dchk.ok{color:#4ea8ff;border-color:#4ea8ff}
`;

  let box = null;
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
    box.className = "dchk hidden";
    host.insertBefore(box, anchor);
    return true;
  }

  function assess(scan){
    const labels = scan?.labels || {};
    const rows = Number(scan?.n_samples) || 0;
    const present = Object.keys(labels).filter(key => Number(labels[key]) > 0);
    if(rows < THIN_ROWS) return {level:"bad", key:"thin"};
    // A single-class site is normal in deployment — a specialist clinic sees only ASD, a
    // mainstream kindergarten only TD — and costs nothing once the cohort covers both, because
    // the coordinator sums leaf counts rather than averaging models. Flag it to check, not to stop.
    if(present.length < 2) return {level:"warn", key:"one_class"};
    if(rows < LEAN_ROWS) return {level:"warn", key:"lean"};
    return {level:"ok", key:"ok"};
  }

  function render(detail){
    if(!mount()) return;
    const scan = detail?.scan;
    if(!scan?.ok){ box.classList.add("hidden"); return; }
    const {level, key} = assess(scan);
    const labels = scan.labels || {};
    const counts = Object.keys(labels).sort()
      .map(name => `${name} ${labels[name]}`).join(" · ");
    box.className = `dchk ${level}`;
    box.innerHTML = `<div class="dchk-title">${s(key)}</div>` +
      `<div class="dchk-why">${s(`${key}_why`)}</div>` +
      `<div class="dchk-nums">${scan.n_samples} ${s("rows")} · ${counts} · ${s("note")}</div>`;
  }

  let last = null;
  document.addEventListener("gbadf:scan", event => { last = event.detail; render(last); });
  // client.js sets documentElement.lang whenever the language changes
  new MutationObserver(() => { if(last) render(last); })
    .observe(document.documentElement, {attributes:true, attributeFilter:["lang"]});
})();
