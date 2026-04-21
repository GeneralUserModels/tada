export const SAMPLE_TADA_HTML = `<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
  :root {
    --sage: #84B179;
    --fern: #A2CB8B;
    --mint: #C7EABB;
    --cream: #E8F5BD;
    --bg: #F4F2EE;
    --bg-warm: #EBE8E2;
    --text: #2C3A28;
    --text-secondary: #6B7A65;
    --text-tertiary: #9BA896;
    --border: rgba(132,177,121,0.22);
    --sage-soft: rgba(132,177,121,0.14);
  }
  *, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }
  html, body { height: 100%; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', system-ui, sans-serif;
    background: var(--bg);
    color: var(--text);
    font-size: 12px;
    line-height: 1.45;
    padding: 12px 14px;
    -webkit-font-smoothing: antialiased;
  }
  header {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    margin-bottom: 8px;
  }
  h1 { font-size: 14px; font-weight: 640; letter-spacing: -0.2px; }
  .date { color: var(--text-tertiary); font-size: 10.5px; }

  .trail {
    display: flex;
    align-items: center;
    gap: 5px;
    font-size: 10px;
    margin-bottom: 10px;
    flex-wrap: wrap;
  }
  .step { color: var(--text-tertiary); }
  .step.done { color: var(--sage); font-weight: 550; }
  .step.current {
    color: white;
    background: var(--sage);
    padding: 2px 8px;
    border-radius: 99px;
    font-weight: 600;
  }
  .chev { color: var(--text-tertiary); font-size: 10px; opacity: 0.7; }

  .section-title {
    font-size: 9.5px;
    font-weight: 700;
    color: var(--text-tertiary);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin: 4px 0 6px;
  }

  .choices {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
    margin-bottom: 10px;
  }
  .choice {
    background: rgba(255,255,255,0.6);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 8px 10px 9px;
    cursor: pointer;
    transition: all 0.15s;
    display: flex;
    flex-direction: column;
  }
  .choice:hover:not(.chosen):not(.muted) {
    border-color: var(--sage);
    background: rgba(255,255,255,0.9);
  }
  .choice.chosen {
    border-color: var(--sage);
    background: rgba(132,177,121,0.14);
    box-shadow: inset 0 0 0 1px var(--sage);
  }
  .choice.muted { opacity: 0.45; }
  .choice-title { font-size: 11.5px; font-weight: 620; margin-bottom: 1px; color: var(--text); }
  .choice-meta { font-size: 9.5px; color: var(--text-tertiary); margin-bottom: 4px; }
  .choice-body { font-size: 10.5px; color: var(--text-secondary); margin-bottom: 6px; flex: 1; }
  .choice-action {
    align-self: flex-start;
    font-size: 9.5px;
    font-weight: 650;
    color: var(--sage);
    padding: 2px 9px;
    border-radius: 99px;
    background: var(--sage-soft);
    transition: all 0.15s;
  }
  .choice.chosen .choice-action { background: var(--sage); color: white; }
  .choice.chosen .choice-action::after { content: ' \u2713'; }

  .party {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 5px 12px;
    margin-bottom: 6px;
  }
  .companion {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 10px;
    color: var(--text-secondary);
  }
  .companion b { font-weight: 620; color: var(--text); }
  .quest { color: var(--text-tertiary); font-style: italic; }
  .bar {
    flex: 1;
    height: 3px;
    background: var(--sage-soft);
    border-radius: 2px;
    overflow: hidden;
    min-width: 24px;
  }
  .bar i {
    display: block;
    height: 100%;
    background: var(--sage);
    border-radius: 2px;
  }

  .commit {
    margin-top: 4px;
    font-size: 10px;
    color: var(--sage);
    font-weight: 600;
    text-align: center;
    padding: 5px 10px;
    background: rgba(132,177,121,0.08);
    border: 1px dashed var(--border);
    border-radius: 6px;
  }
</style>
</head>
<body>
<header>
  <h1>Yellow Brick Road</h1>
  <span class="date">Day 3 &middot; Quadling fields</span>
</header>

<div class="trail">
  <span class="step done">Kansas &#10003;</span>
  <span class="chev">&rsaquo;</span>
  <span class="step done">Munchkin &#10003;</span>
  <span class="chev">&rsaquo;</span>
  <span class="step current">Quadling</span>
  <span class="chev">&rsaquo;</span>
  <span class="step">Poppy</span>
  <span class="chev">&rsaquo;</span>
  <span class="step">Emerald</span>
</div>

<div class="section-title">Next leg &middot; pick a path</div>

<div class="choices">
  <div class="choice" data-id="poppy">
    <div class="choice-title">Through the poppy field</div>
    <div class="choice-meta">~5 hr &middot; risky</div>
    <div class="choice-body">Fastest line. Tin Man &amp; Scarecrow unaffected. Dorothy &amp; Lion will drop unless Glinda's breeze holds.</div>
    <span class="choice-action">Select</span>
  </div>
  <div class="choice" data-id="hedgerow">
    <div class="choice-title">Hedgerow detour</div>
    <div class="choice-meta">~9 hr &middot; safe</div>
    <div class="choice-body">Clear path. Party reaches Emerald gates by dusk &mdash; still in time for Thursday's audience.</div>
    <span class="choice-action">Select</span>
  </div>
</div>

<div class="party">
  <span class="companion"><b>Dorothy</b><span class="quest">home</span><span class="bar"><i style="width:25%"></i></span></span>
  <span class="companion"><b>Scarecrow</b><span class="quest">brain</span><span class="bar"><i style="width:40%"></i></span></span>
  <span class="companion"><b>Tin Man</b><span class="quest">heart</span><span class="bar"><i style="width:60%"></i></span></span>
  <span class="companion"><b>Lion</b><span class="quest">courage</span><span class="bar"><i style="width:30%"></i></span></span>
</div>

<div class="commit" id="commit" hidden></div>

<script>
  var choices = document.querySelectorAll('.choice');
  var commit = document.getElementById('commit');
  var messages = {
    poppy: "Committed: through the poppies. Stocking antidote herbs at dusk.",
    hedgerow: "Committed: hedgerow detour. ETA Emerald City \u2014 Thursday dusk."
  };
  choices.forEach(function(c){
    c.addEventListener('click', function(){
      if (c.classList.contains('chosen')) {
        choices.forEach(function(x){ x.classList.remove('chosen','muted'); });
        commit.hidden = true;
        return;
      }
      var id = c.getAttribute('data-id');
      choices.forEach(function(x){
        if (x === c) { x.classList.add('chosen'); x.classList.remove('muted'); }
        else { x.classList.add('muted'); x.classList.remove('chosen'); }
      });
      commit.textContent = messages[id];
      commit.hidden = false;
    });
  });
</script>
</body>
</html>`;
