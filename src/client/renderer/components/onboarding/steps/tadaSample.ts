export const SAMPLE_TADA_HTML = `<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
  :root {
    --sage: #84B179;
    --fern: #A2CB8B;
    --mint: #C7EABB;
    --bg: #F4F2EE;
    --paper: rgba(255,255,255,0.55);
    --text: #2C3A28;
    --text-secondary: #6B7A65;
    --text-tertiary: #9BA896;
    --border: rgba(132,177,121,0.22);
    --sage-soft: rgba(132,177,121,0.14);
    --sage-strong: rgba(132,177,121,0.22);
    --amber: #B98838;
    --amber-soft: rgba(185,136,56,0.16);
    --neutral: #8A9186;
    --neutral-soft: rgba(138,145,134,0.14);
  }
  *, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }
  html, body { height: 100%; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', system-ui, sans-serif;
    background: var(--bg);
    color: var(--text);
    font-size: 11px;
    line-height: 1.35;
    padding: 8px 11px;
    -webkit-font-smoothing: antialiased;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }

  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    margin-bottom: 6px;
  }
  .head-left { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
  h1 { font-size: 13px; font-weight: 680; letter-spacing: -0.2px; }
  .date { color: var(--text-tertiary); font-size: 9.5px; }
  .chip {
    font-size: 9px;
    font-weight: 650;
    padding: 2px 8px;
    border-radius: 99px;
    background: var(--sage-soft);
    color: var(--sage);
    white-space: nowrap;
  }

  .tabs {
    display: flex;
    gap: 0;
    border-bottom: 1px solid var(--border);
    margin-bottom: 6px;
  }
  .tab {
    background: none;
    border: none;
    padding: 4px 10px 6px;
    font-size: 10.5px;
    font-weight: 620;
    color: var(--text-tertiary);
    cursor: pointer;
    border-bottom: 2px solid transparent;
    margin-bottom: -1px;
    white-space: nowrap;
    font-family: inherit;
    transition: color 0.12s, border-color 0.12s;
    letter-spacing: -0.1px;
  }
  .tab:hover { color: var(--text-secondary); }
  .tab.active {
    color: var(--sage);
    border-bottom-color: var(--sage);
  }

  .panels { flex: 1; min-height: 0; overflow: hidden; }
  .panel { display: none; }
  .panel.active { display: block; animation: fade 0.18s ease; }
  @keyframes fade {
    from { opacity: 0; transform: translateY(2px); }
    to { opacity: 1; transform: translateY(0); }
  }

  /* Today */
  .row {
    display: flex;
    align-items: baseline;
    gap: 10px;
    padding: 3px 0;
    border-bottom: 1px solid rgba(132,177,121,0.08);
  }
  .row:last-child { border-bottom: none; }
  .lbl {
    color: var(--text-tertiary);
    font-size: 8.5px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-weight: 700;
    width: 60px;
    flex-shrink: 0;
  }
  .val {
    color: var(--text);
    font-size: 10.5px;
    line-height: 1.35;
    min-width: 0;
  }
  .val em { color: var(--sage); font-style: normal; font-weight: 620; }

  /* People / Places entries */
  .entry-list { display: flex; flex-direction: column; gap: 3px; }
  .entry {
    display: grid;
    grid-template-columns: 12px 1fr auto;
    gap: 8px;
    padding: 4px 8px;
    background: var(--paper);
    border: 1px solid var(--border);
    border-radius: 7px;
    align-items: center;
  }
  .dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--sage);
    justify-self: center;
  }
  .dot.friendly { background: var(--fern); }
  .dot.hostile  { background: var(--amber); box-shadow: 0 0 0 3px var(--amber-soft); }
  .dot.watchful { background: var(--neutral); }

  .entry-body { min-width: 0; display: flex; flex-direction: column; gap: 0px; }
  .entry-head {
    display: flex;
    align-items: baseline;
    gap: 7px;
    font-size: 10.5px;
  }
  .entry-name {
    font-weight: 640;
    color: var(--text);
    white-space: nowrap;
  }
  .entry-when {
    color: var(--text-tertiary);
    font-size: 9px;
  }
  .entry-note {
    color: var(--text-secondary);
    font-size: 9.5px;
    line-height: 1.3;
  }

  .tag {
    font-size: 8.5px;
    font-weight: 650;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    padding: 1px 7px;
    border-radius: 99px;
    white-space: nowrap;
    justify-self: end;
    background: var(--sage-soft);
    color: var(--sage);
  }
  .tag.hostile  { background: var(--amber-soft); color: var(--amber); }
  .tag.watchful { background: var(--neutral-soft); color: var(--neutral); }
  .tag.friendly { background: rgba(162,203,139,0.22); color: #638a56; }

  /* Home leads */
  .leads { display: flex; flex-direction: column; gap: 6px; }
  .lead {
    padding: 5px 9px 6px;
    background: var(--paper);
    border: 1px solid var(--border);
    border-radius: 7px;
  }
  .lead-top {
    display: flex;
    align-items: baseline;
    gap: 8px;
    margin-bottom: 3px;
  }
  .conf {
    font-size: 11px;
    font-weight: 700;
    color: var(--sage);
    letter-spacing: -0.2px;
    width: 28px;
    flex-shrink: 0;
  }
  .conf.mid { color: var(--fern); }
  .conf.low { color: var(--neutral); }
  .lead-title {
    font-size: 10.5px;
    color: var(--text);
    font-style: italic;
    flex: 1;
    min-width: 0;
    line-height: 1.3;
  }
  .lead-bar {
    height: 2px;
    background: rgba(132,177,121,0.12);
    border-radius: 1px;
    overflow: hidden;
    margin: 3px 0 3px 36px;
  }
  .lead-bar i {
    display: block;
    height: 100%;
    background: var(--sage);
    border-radius: 1px;
  }
  .lead-bar i.mid { background: var(--fern); }
  .lead-bar i.low { background: var(--neutral); }
  .lead-meta {
    font-size: 9px;
    color: var(--text-tertiary);
    margin-left: 36px;
  }
</style>
</head>
<body>
<header>
  <div class="head-left">
    <h1>Field Guide &middot; Oz</h1>
    <span class="date">Dorothy Gale &middot; Day 12</span>
  </div>
  <span class="chip">daily &middot; at dawn</span>
</header>

<div class="tabs">
  <button class="tab active" data-tab="today">Today</button>
  <button class="tab" data-tab="people">People</button>
  <button class="tab" data-tab="places">Places</button>
  <button class="tab" data-tab="leads">Home leads</button>
</div>

<div class="panels">
  <div class="panel active" id="panel-today">
    <div class="row">
      <span class="lbl">Location</span>
      <span class="val">Quadling fields &middot; 3 mi from the <em>Emerald Gate</em></span>
    </div>
    <div class="row">
      <span class="lbl">Weather</span>
      <span class="val">Sunny at dawn, showers after noon</span>
    </div>
    <div class="row">
      <span class="lbl">Party</span>
      <span class="val">Scarecrow, Tin Man, Lion, Toto &mdash; all here</span>
    </div>
    <div class="row">
      <span class="lbl">Morning</span>
      <span class="val">Arrive at the gate, take a number for the Wizard's audience</span>
    </div>
    <div class="row">
      <span class="lbl">Dusk</span>
      <span class="val">Glinda said she'd send word by owl before nightfall</span>
    </div>
    <div class="row">
      <span class="lbl">Noted</span>
      <span class="val">A Munchkin child pressed a paper shoe into her hand at dawn</span>
    </div>
  </div>

  <div class="panel" id="panel-people">
    <div class="entry-list">
      <div class="entry">
        <span class="dot"></span>
        <div class="entry-body">
          <div class="entry-head">
            <span class="entry-name">Scarecrow</span>
            <span class="entry-when">met day 2</span>
          </div>
          <div class="entry-note">Straw-filled; thinks a little faster every day.</div>
        </div>
        <span class="tag">ally</span>
      </div>
      <div class="entry">
        <span class="dot"></span>
        <div class="entry-body">
          <div class="entry-head">
            <span class="entry-name">Tin Man</span>
            <span class="entry-when">met day 4</span>
          </div>
          <div class="entry-note">Oil every morning; the kindest heart out here.</div>
        </div>
        <span class="tag">ally</span>
      </div>
      <div class="entry">
        <span class="dot"></span>
        <div class="entry-body">
          <div class="entry-head">
            <span class="entry-name">Cowardly Lion</span>
            <span class="entry-when">met day 6</span>
          </div>
          <div class="entry-note">Covers his eyes in the dark but wakes first.</div>
        </div>
        <span class="tag">ally</span>
      </div>
      <div class="entry">
        <span class="dot friendly"></span>
        <div class="entry-body">
          <div class="entry-head">
            <span class="entry-name">Glinda</span>
            <span class="entry-when">met day 3</span>
          </div>
          <div class="entry-note">Arrived in a bubble; says the Wizard sends travelers home.</div>
        </div>
        <span class="tag friendly">friendly</span>
      </div>
      <div class="entry">
        <span class="dot hostile"></span>
        <div class="entry-body">
          <div class="entry-head">
            <span class="entry-name">West Witch</span>
            <span class="entry-when">sighted day 8</span>
          </div>
          <div class="entry-note">100-coin bounty posted; watches from her tower.</div>
        </div>
        <span class="tag hostile">hostile</span>
      </div>
    </div>
  </div>

  <div class="panel" id="panel-places">
    <div class="entry-list">
      <div class="entry">
        <span class="dot"></span>
        <div class="entry-body">
          <div class="entry-head">
            <span class="entry-name">Munchkinland</span>
            <span class="entry-when">day 1 &ndash; 2</span>
          </div>
          <div class="entry-note">Blue cloaks, grateful crowds. The house landed here.</div>
        </div>
        <span class="tag">safe</span>
      </div>
      <div class="entry">
        <span class="dot hostile"></span>
        <div class="entry-body">
          <div class="entry-head">
            <span class="entry-name">Poppy field</span>
            <span class="entry-when">day 5</span>
          </div>
          <div class="entry-note">Sleep spell under the petals; Glinda's snow woke us.</div>
        </div>
        <span class="tag hostile">risky</span>
      </div>
      <div class="entry">
        <span class="dot"></span>
        <div class="entry-body">
          <div class="entry-head">
            <span class="entry-name">Tin Grove</span>
            <span class="entry-when">day 4</span>
          </div>
          <div class="entry-note">Rusted tools, one kind woodsman, quiet weather.</div>
        </div>
        <span class="tag">safe</span>
      </div>
      <div class="entry">
        <span class="dot friendly"></span>
        <div class="entry-body">
          <div class="entry-head">
            <span class="entry-name">Quadling fields</span>
            <span class="entry-when">day 11 &ndash; now</span>
          </div>
          <div class="entry-note">Red earth, friendly villages, sisters of Glinda about.</div>
        </div>
        <span class="tag friendly">friendly</span>
      </div>
      <div class="entry">
        <span class="dot watchful"></span>
        <div class="entry-body">
          <div class="entry-head">
            <span class="entry-name">Emerald Gate</span>
            <span class="entry-when">day 13 &rarr;</span>
          </div>
          <div class="entry-note">First guardhouse to the Wizard. Long queue, sharp questions.</div>
        </div>
        <span class="tag watchful">ahead</span>
      </div>
    </div>
  </div>

  <div class="panel" id="panel-leads">
    <div class="leads">
      <div class="lead">
        <div class="lead-top">
          <span class="conf">72%</span>
          <span class="lead-title">&ldquo;The Wizard sends travelers home.&rdquo;</span>
          <span class="tag">pursuing</span>
        </div>
        <div class="lead-bar"><i style="width:72%"></i></div>
        <div class="lead-meta">Glinda &middot; day 3</div>
      </div>
      <div class="lead">
        <div class="lead-top">
          <span class="conf mid">55%</span>
          <span class="lead-title">&ldquo;A weekly balloon leaves the Emerald City.&rdquo;</span>
          <span class="tag friendly">ask at gate</span>
        </div>
        <div class="lead-bar"><i class="mid" style="width:55%"></i></div>
        <div class="lead-meta">Inn gossip &middot; day 10</div>
      </div>
      <div class="lead">
        <div class="lead-top">
          <span class="conf mid">40%</span>
          <span class="lead-title">&ldquo;The slippers warm at dusk, facing east.&rdquo;</span>
          <span class="tag watchful">watch tonight</span>
        </div>
        <div class="lead-bar"><i class="mid" style="width:40%"></i></div>
        <div class="lead-meta">Noticed herself &middot; day 7</div>
      </div>
      <div class="lead">
        <div class="lead-top">
          <span class="conf low">18%</span>
          <span class="lead-title">&ldquo;Tornadoes remember their first calling.&rdquo;</span>
          <span class="tag watchful">folklore</span>
        </div>
        <div class="lead-bar"><i class="low" style="width:18%"></i></div>
        <div class="lead-meta">A Munchkin elder &middot; day 2</div>
      </div>
    </div>
  </div>
</div>

<script>
  (function(){
    function setTab(id){
      var tabs = document.getElementsByClassName('tab');
      for (var i = 0; i < tabs.length; i++) {
        tabs[i].classList.toggle('active', tabs[i].getAttribute('data-tab') === id);
      }
      var panels = document.getElementsByClassName('panel');
      for (var j = 0; j < panels.length; j++) {
        panels[j].classList.toggle('active', panels[j].id === 'panel-' + id);
      }
    }
    function init(){
      document.body.addEventListener('click', function(e){
        var t = e.target;
        while (t && t !== document.body) {
          if (t.classList && t.classList.contains('tab')) {
            setTab(t.getAttribute('data-tab'));
            return;
          }
          t = t.parentNode;
        }
      });
    }
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', init);
    } else {
      init();
    }
  })();
</script>
</body>
</html>`;
