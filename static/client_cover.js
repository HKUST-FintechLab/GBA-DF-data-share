/* Optional add-on: an opening cover for the desktop client.
 *
 * Purely additive and self-contained — its own DOM, CSS and strings, injected as an overlay on
 * top of the existing first step. It touches no other element and listens to no application
 * state, so deleting this file and its <script> tag in client.html restores the previous
 * behaviour exactly.
 *
 * It exists because the client opens straight into "choose your data type", which assumes the
 * viewer already knows what a data federation is. In a room of people meeting the project for
 * the first time, the first screen has to answer: what is this, why does it exist, and what am
 * I about to watch.
 *
 * The wording follows the federation's own honesty guardrails: raw records stay local (never
 * "nothing leaves") and privacy is epsilon-bounded (never "impossible to leak"). The cover makes
 * no claim about accuracy, so whoever presents it still has to say out loud that the cohorts and
 * metrics behind the demo are synthetic.
 */
(() => {
  const STRINGS = {
    en: {
      wordmark: "GBA·DF",
      full: "Greater Bay Area Data Federation",
      lede: "Share what the data can tell you — without handing over the data.",
      how: "What you are about to see",
      pillars: [
        ["Data stays put", "Raw recordings never leave the machine that collected them."],
        ["Privacy you can count", "Every model update carries calibrated noise against a metered ε-budget."],
        ["Signed and auditable", "Every step is signed into a chain where any edit shows up."]
      ],
      start: "Start"
    },
    zh: {
      wordmark: "GBA·DF",
      full: "大湾区数据联邦",
      lede: "共享数据的价值 —— 而不用把数据交出去。",
      how: "接下来你会看到",
      pillars: [
        ["数据不动", "原始录制始终留在采集它的那台机器上。"],
        ["隐私可以计量", "每一次模型更新都带校准噪声，并计入 ε 预算账本。"],
        ["签名可审计", "每一步都签名写入哈希链，任何改动都会被发现。"]
      ],
      start: "开始"
    },
    "zh-Hant": {
      wordmark: "GBA·DF",
      full: "大灣區資料聯邦",
      lede: "共享資料的價值 —— 而不用把資料交出去。",
      how: "接下來你會看到",
      pillars: [
        ["資料不動", "原始錄製始終留在採集它的那台機器上。"],
        ["隱私可以計量", "每一次模型更新都帶校準雜訊，並計入 ε 預算帳本。"],
        ["簽名可稽核", "每一步都簽名寫入雜湊鏈，任何改動都會被發現。"]
      ],
      start: "開始"
    }
  };

  const CSS = `
/* Three accents, one per promise, all already in the console palette: blue for the data that
   stays put, amber for the privacy budget (the same amber the epsilon bar uses), mint for the
   audit chain. Enough colour to separate the three ideas, not enough to become a new theme. */
.cover{position:fixed;inset:0;z-index:60;display:grid;place-items:center;padding:5vh 4vw;
  overflow:auto;background:#0d1a2e;
  background-image:
    radial-gradient(52% 40% at 16% 82%,rgba(255,169,92,.07) 0%,transparent 70%),
    radial-gradient(46% 38% at 86% 76%,rgba(86,214,164,.06) 0%,transparent 72%),
    radial-gradient(120% 90% at 50% 6%,#1e365d 0%,#0d1a2e 62%);
  animation:coverIn .5s ease}
.cover.hidden{display:none}
@keyframes coverIn{from{opacity:0}to{opacity:1}}
.cover-inner{width:min(1000px,100%);text-align:center;color:#eaf1fc}
.cover-mark{font:300 clamp(52px,9vw,104px)/1 Georgia,'Songti SC',serif;letter-spacing:.06em;
  color:#f3f7ff}
.cover-full{margin-top:20px;color:#66809f;
  font:10.5px 'SF Mono',Consolas,ui-monospace,monospace;letter-spacing:.42em;text-transform:uppercase}
.cover-rule{width:120px;height:1px;margin:40px auto;background:linear-gradient(90deg,
  transparent,rgba(78,168,255,.6),rgba(255,169,92,.6),rgba(86,214,164,.6),transparent)}
.cover-lede{max-width:800px;margin:0 auto;
  font:300 clamp(20px,2.5vw,30px)/1.75 Georgia,'Songti SC',serif;color:#eaf1fc;
  letter-spacing:.01em}
.cover-how{margin-top:72px;color:#3c6fa8;
  font:9.5px 'SF Mono',Consolas,monospace;letter-spacing:.28em;text-transform:uppercase}
.cover-pillars{display:grid;grid-template-columns:repeat(3,1fr);gap:26px;margin-top:26px;
  max-width:880px;margin-left:auto;margin-right:auto;text-align:left}
.cover-pillar{position:relative;padding:26px 22px 24px;border:1px solid rgba(122,168,235,.14);
  border-top:1px solid var(--pillar);background:rgba(13,26,46,.42)}
/* the tint is a progressive enhancement: an engine without color-mix keeps the flat panel above */
.cover-pillar{background:
    linear-gradient(180deg,color-mix(in srgb,var(--pillar) 7%,transparent) 0%,transparent 58%),
    rgba(13,26,46,.42)}
.cover-pillar::before{content:"";position:absolute;left:-1px;top:-1px;width:11px;height:11px;
  border-left:1px solid var(--pillar);border-top:1px solid var(--pillar)}
.cover-pillar i{display:block;margin-bottom:14px;color:var(--pillar);font-style:normal;
  font:10px 'SF Mono',Consolas,monospace;letter-spacing:.22em}
.cover-pillar b{display:block;color:#f3f7ff;font:500 16px/1.45 Georgia,'Songti SC',serif;
  letter-spacing:.01em}
.cover-pillar span{display:block;margin-top:14px;color:#93abcc;
  font:10px/2.05 'SF Mono',Consolas,monospace}
.cover-start{margin-top:62px;padding:15px 52px;border:1px solid rgba(78,168,255,.55);
  border-radius:4px;background:rgba(78,168,255,.08);color:#eaf1fc;cursor:pointer;
  font:12px 'SF Mono',Consolas,monospace;letter-spacing:.32em;text-transform:uppercase;
  transition:.2s}
.cover-start:hover{background:rgba(78,168,255,.2);border-color:#4ea8ff;
  box-shadow:0 0 24px rgba(78,168,255,.22)}
@media (max-width:820px){
  .cover-pillars{grid-template-columns:1fr;max-width:420px}
}

/* the classic interface keeps its own light palette */
html[data-theme="classic"] .cover{background:#f7faf9;background-image:
  radial-gradient(120% 90% at 50% 8%,#ffffff 0%,#eef4f2 70%)}
html[data-theme="classic"] .cover-inner{color:#1f2222}
html[data-theme="classic"] .cover-mark{color:#17324d}
html[data-theme="classic"] .cover-full{color:#6b7a78}
html[data-theme="classic"] .cover-lede{color:#22312e}
html[data-theme="classic"] .cover-rule{background:rgba(59,123,191,.45)}
html[data-theme="classic"] .cover-how{color:#3b7bbf}
html[data-theme="classic"] .cover-pillar{border-color:#dfe6e5;border-top-color:var(--pillar);
  background:#fff}
html[data-theme="classic"] .cover-pillar{background:
  linear-gradient(180deg,color-mix(in srgb,var(--pillar) 8%,transparent) 0%,transparent 56%),#fff}
html[data-theme="classic"] .cover-pillar b{color:#17324d}
html[data-theme="classic"] .cover-pillar span{color:#6b7a78}
html[data-theme="classic"] .cover-start{color:#17324d;border-color:rgba(59,123,191,.5);
  background:rgba(59,123,191,.08)}
`;

  // data stays put · privacy budget · audit chain
  const ACCENTS = ["#4ea8ff", "#ffa95c", "#56d6a4"];

  let box = null;
  const lang = () => {
    const value = document.documentElement.lang || "en";
    return STRINGS[value] ? value : "en";
  };

  function render(){
    const s = STRINGS[lang()];
    box.innerHTML =
      '<div class="cover-inner">' +
        `<div class="cover-mark">${s.wordmark}</div>` +
        `<div class="cover-full">${s.full}</div>` +
        '<div class="cover-rule"></div>' +
        `<p class="cover-lede">${s.lede}</p>` +
        `<div class="cover-how">${s.how}</div>` +
        '<div class="cover-pillars">' +
          s.pillars.map(([title, body], index) =>
            `<div class="cover-pillar" style="--pillar:${ACCENTS[index]}">` +
              `<i>${String(index + 1).padStart(2, "0")}</i>` +
              `<b>${title}</b><span>${body}</span></div>`).join("") +
        '</div>' +
        `<button type="button" class="cover-start">${s.start}</button>` +
      '</div>';
    box.querySelector(".cover-start").onclick = dismiss;
  }

  function dismiss(){
    box.classList.add("hidden");
    document.removeEventListener("keydown", onKey);
  }
  function onKey(event){
    if(event.key === "Escape" || event.key === "Enter") dismiss();
  }

  function mount(){
    const style = document.createElement("style");
    style.textContent = CSS;
    document.head.appendChild(style);
    box = document.createElement("div");
    box.className = "cover";
    document.body.appendChild(box);
    render();
    document.addEventListener("keydown", onKey);
    // client.js sets documentElement.lang whenever the language changes
    new MutationObserver(() => { if(!box.classList.contains("hidden")) render(); })
      .observe(document.documentElement, {attributes:true, attributeFilter:["lang"]});
  }

  if(document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount);
  else mount();
})();
