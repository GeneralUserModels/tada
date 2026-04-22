export const SAMPLE_PENSIEVE_HTML = `<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
  :root {
    --sage: #84B179;
    --fern: #A2CB8B;
    --mint: #C7EABB;
    --bg: #F4F2EE;
    --paper: rgba(255,255,255,0.6);
    --text: #2C3A28;
    --text-secondary: #6B7A65;
    --text-tertiary: #9BA896;
    --border: rgba(132,177,121,0.22);
    --sage-soft: rgba(132,177,121,0.14);
    --sage-strong: rgba(132,177,121,0.22);
    --amber: #B98838;
    --amber-soft: rgba(185,136,56,0.16);
  }
  *, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }
  html, body { height: 100%; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', system-ui, sans-serif;
    background: var(--bg);
    color: var(--text);
    font-size: 11px;
    line-height: 1.38;
    padding: 8px 11px;
    -webkit-font-smoothing: antialiased;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }

  /* ── List header (search + status) ─────────────────── */
  .list-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    margin-bottom: 8px;
  }
  .search-wrap {
    position: relative;
    flex: 1;
    max-width: 260px;
  }
  .search-icon {
    position: absolute;
    left: 8px; top: 50%;
    transform: translateY(-50%);
    color: var(--text-tertiary);
    pointer-events: none;
  }
  .search {
    width: 100%;
    padding: 4px 10px 4px 24px;
    font-size: 10.5px;
    font-family: inherit;
    color: var(--text);
    background: rgba(255,255,255,0.6);
    border: 1px solid var(--border);
    border-radius: 99px;
    outline: none;
  }
  .search::placeholder { color: var(--text-tertiary); }
  .search:focus {
    background: rgba(255,255,255,0.85);
    border-color: rgba(132,177,121,0.35);
  }
  .status {
    font-size: 9.5px;
    color: var(--text-tertiary);
    white-space: nowrap;
  }
  .status b {
    font-weight: 620;
    color: var(--text-secondary);
  }

  /* ── Category 2×2 grid ─────────────────────────────── */
  .grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px 12px;
    flex: 1;
    min-height: 0;
  }
  .cat-group {
    display: flex;
    flex-direction: column;
    gap: 4px;
    min-width: 0;
  }
  .cat-label {
    font-size: 8.5px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-tertiary);
    padding: 0 2px;
  }
  .card {
    background: var(--paper);
    border: 1px solid var(--border);
    border-radius: 9px;
    padding: 7px 10px 8px;
    cursor: pointer;
    transition: border-color 0.15s, background 0.15s, transform 0.12s, box-shadow 0.15s;
  }
  .card:hover {
    border-color: rgba(132,177,121,0.42);
    background: rgba(255,255,255,0.85);
    transform: translateY(-1px);
    box-shadow: 0 2px 6px rgba(132,177,121,0.08);
  }
  .card-head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 6px;
    margin-bottom: 3px;
  }
  .card-title {
    font-size: 11.5px;
    font-weight: 640;
    color: var(--text);
    letter-spacing: -0.15px;
    line-height: 1.25;
    min-width: 0;
  }
  .conf {
    font-size: 9px;
    font-weight: 700;
    padding: 1px 6px;
    border-radius: 99px;
    white-space: nowrap;
    flex-shrink: 0;
  }
  .conf.high { background: rgba(132,177,121,0.18); color: var(--sage); }
  .conf.mid  { background: rgba(162,203,139,0.22); color: #6a9a5d; }
  .conf.low  { background: var(--amber-soft);     color: var(--amber); }
  .card-date {
    font-size: 9.5px;
    color: var(--text-tertiary);
  }

  /* ── Detail view ───────────────────────────────────── */
  .detail { display: none; flex-direction: column; flex: 1; min-height: 0; }
  .detail.active { display: flex; }
  .list { display: flex; flex-direction: column; flex: 1; min-height: 0; }
  .list.hidden { display: none; }

  .detail-head {
    display: flex;
    align-items: center;
    gap: 8px;
    padding-bottom: 5px;
    margin-bottom: 5px;
    border-bottom: 1px solid var(--border);
  }
  .back-btn {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    padding: 2px 8px 2px 5px;
    font-size: 10px;
    font-weight: 620;
    color: var(--text-secondary);
    background: var(--paper);
    border: 1px solid var(--border);
    border-radius: 99px;
    cursor: pointer;
    font-family: inherit;
  }
  .back-btn:hover {
    color: var(--sage);
    border-color: var(--sage);
    background: var(--sage-soft);
  }
  .crumb {
    display: flex;
    align-items: baseline;
    gap: 5px;
    min-width: 0;
    flex: 1;
  }
  .crumb-cat {
    font-size: 8.5px;
    font-weight: 650;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    padding: 1px 6px;
    border-radius: 99px;
    background: var(--sage-soft);
    color: var(--sage);
    flex-shrink: 0;
  }
  .crumb-title {
    font-size: 12.5px;
    font-weight: 650;
    color: var(--text);
    letter-spacing: -0.15px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .detail-meta {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-shrink: 0;
  }
  .detail-date {
    font-size: 9.5px;
    color: var(--text-tertiary);
  }
  .detail-body {
    flex: 1;
    min-height: 0;
    overflow: hidden;
  }
  .intro {
    color: var(--text);
    margin-bottom: 6px;
  }
  .sec-title {
    font-size: 8.5px;
    font-weight: 700;
    color: var(--text-tertiary);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin: 6px 0 3px;
  }
  .detail-body ul { list-style: none; padding: 0; margin: 0; }
  .detail-body li {
    color: var(--text-secondary);
    padding-left: 11px;
    position: relative;
    margin-bottom: 2px;
  }
  .detail-body li::before {
    content: '';
    position: absolute;
    left: 3px; top: 7px;
    width: 3px; height: 3px;
    border-radius: 50%;
    background: var(--sage);
    opacity: 0.6;
  }
  a.wl {
    color: var(--sage);
    text-decoration: underline dotted;
    text-decoration-thickness: 1px;
    text-underline-offset: 2px;
    cursor: pointer;
    font-weight: 550;
  }
  a.wl:hover { color: #5a8c4f; text-decoration-style: solid; }
</style>
</head>
<body>
  <div class="list" id="list">
    <div class="list-header">
      <div class="search-wrap">
        <svg class="search-icon" width="11" height="11" viewBox="0 0 14 14" fill="none">
          <circle cx="6" cy="6" r="4.2" stroke="currentColor" stroke-width="1.2"/>
          <path d="M9.4 9.4 13 13" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>
        </svg>
        <input class="search" type="text" placeholder="Search pages..." />
      </div>
      <div class="status"><b>4</b> pages &middot; updated today</div>
    </div>

    <div class="grid">
      <div class="cat-group">
        <div class="cat-label">People</div>
        <div class="card" data-link="hermione">
          <div class="card-head">
            <div class="card-title">Hermione Granger</div>
            <span class="conf high">94%</span>
          </div>
          <div class="card-date">Oct 19, 1997</div>
        </div>
      </div>
      <div class="cat-group">
        <div class="cat-label">Projects</div>
        <div class="card" data-link="horcrux">
          <div class="card-head">
            <div class="card-title">Horcrux Hunt</div>
            <span class="conf mid">72%</span>
          </div>
          <div class="card-date">Nov 2, 1997</div>
        </div>
      </div>
      <div class="cat-group">
        <div class="cat-label">Interests</div>
        <div class="card" data-link="dada">
          <div class="card-head">
            <div class="card-title">Defense Against the Dark Arts</div>
            <span class="conf mid">58%</span>
          </div>
          <div class="card-date">Sep 28, 1997</div>
        </div>
      </div>
      <div class="cat-group">
        <div class="cat-label">Notes</div>
        <div class="card" data-link="snape">
          <div class="card-head">
            <div class="card-title">Suspicions about Snape</div>
            <span class="conf low">28%</span>
          </div>
          <div class="card-date">Oct 11, 1997</div>
        </div>
      </div>
    </div>
  </div>

  <div class="detail" id="detail">
    <div class="detail-head">
      <button class="back-btn" id="back" type="button">
        <svg width="9" height="9" viewBox="0 0 14 14" fill="none">
          <path d="M9 2L4 7l5 5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
        All pages
      </button>
      <div class="crumb">
        <span class="crumb-cat" id="cat"></span>
        <span class="crumb-title" id="title"></span>
      </div>
      <div class="detail-meta">
        <span class="conf" id="conf"></span>
        <span class="detail-date" id="updated"></span>
      </div>
    </div>
    <div class="detail-body" id="body"></div>
  </div>

<script>
(function(){
  var PAGES = {
    hermione: {
      title: 'Hermione Granger',
      category: 'People',
      conf: 94, confClass: 'high', label: 'certain',
      updated: 'Oct 19, 1997',
      intro: "Closest friend since first year. Muggle-born, top of the class in every subject, and the person most likely to have already read the book before it\u2019s brought up.",
      sections: [
        { t: "What she's working on", b: [
          'Planning the route through the <a class="wl" data-link="horcrux">Horcrux Hunt</a> \u2014 she keeps the itinerary.',
          'Quiet research into house-elf rights (not speaking much about it this year).'
        ]},
        { t: 'Recent shape', b: [
          'Carrying a beaded bag full of supplies, books, and the tent.',
          'Short-tempered whenever <a class="wl" data-link="dada">Defense Against the Dark Arts</a> comes up.'
        ]}
      ]
    },
    horcrux: {
      title: 'Horcrux Hunt',
      category: 'Projects',
      conf: 72, confClass: 'mid', label: 'confident',
      updated: 'Nov 2, 1997',
      intro: 'The open undertaking after Dumbledore\u2019s funeral. Seven fragments of Voldemort\u2019s soul hidden in objects; destroy them all before the final confrontation. <a class="wl" data-link="hermione">Hermione Granger</a> keeps the plan.',
      sections: [
        { t: 'Confirmed', b: [
          'Tom Riddle\u2019s diary \u2014 destroyed, second year.',
          'Marvolo\u2019s ring \u2014 destroyed by Dumbledore; the curse is what killed him.',
          'Slytherin\u2019s locket \u2014 recovered from Grimmauld Place, not yet destroyed.'
        ]},
        { t: 'Still open', b: [
          'The count is a working assumption, not a certainty.',
          'Hogwarts itself may hide one (Ravenclaw\u2019s diadem is the best guess).'
        ]}
      ]
    },
    dada: {
      title: 'Defense Against the Dark Arts',
      category: 'Interests',
      conf: 58, confClass: 'mid', label: 'probable',
      updated: 'Sep 28, 1997',
      intro: 'Strongest subject, and the one worth returning to. Started with Lupin in third year; a new teacher each year has meant piecing most of it together alone.',
      sections: [
        { t: 'Recurring threads', b: [
          'Patronus charm \u2014 the piece that holds up when things go wrong.',
          'Non-verbal spellwork \u2014 came up again planning the <a class="wl" data-link="horcrux">Horcrux Hunt</a> with <a class="wl" data-link="hermione">Hermione</a>.',
          'Spotting dark objects before touching them (the locket was a lesson).'
        ]},
        { t: 'Open questions', b: [
          'How much of the Elder Wand folklore is real?'
        ]}
      ]
    },
    snape: {
      title: 'Suspicions about Snape',
      category: 'Notes',
      conf: 28, confClass: 'low', label: 'speculative',
      updated: 'Oct 11, 1997',
      intro: 'A thread that won\u2019t sit still. Every piece of evidence cuts both ways.',
      sections: [
        { t: 'For trust', b: [
          'Dumbledore\u2019s repeated, unexplained confidence in him.',
          'The Unbreakable Vow arguably protected Draco, not Voldemort.'
        ]},
        { t: 'Against', b: [
          'Killed Dumbledore, in front of witnesses.',
          '<a class="wl" data-link="hermione">Hermione</a> agrees on the facts, not the conclusion.'
        ]}
      ]
    }
  };

  function showDetail(id) {
    var p = PAGES[id];
    if (!p) return;
    document.getElementById('cat').textContent = p.category;
    document.getElementById('title').textContent = p.title;
    var conf = document.getElementById('conf');
    conf.textContent = p.conf + '% ' + p.label;
    conf.className = 'conf ' + p.confClass;
    document.getElementById('updated').textContent = p.updated;

    var body = document.getElementById('body');
    var html = '<p class="intro">' + p.intro + '</p>';
    for (var i = 0; i < p.sections.length; i++) {
      var s = p.sections[i];
      html += '<div class="sec-title">' + s.t + '</div><ul>';
      for (var j = 0; j < s.b.length; j++) {
        html += '<li>' + s.b[j] + '</li>';
      }
      html += '</ul>';
    }
    body.innerHTML = html;

    document.getElementById('list').classList.add('hidden');
    document.getElementById('detail').classList.add('active');
  }

  function showList() {
    document.getElementById('detail').classList.remove('active');
    document.getElementById('list').classList.remove('hidden');
  }

  function init(){
    document.body.addEventListener('click', function(e){
      var t = e.target;
      while (t && t !== document.body) {
        if (t.id === 'back') {
          showList();
          return;
        }
        if (t.getAttribute && t.getAttribute('data-link')) {
          e.preventDefault();
          showDetail(t.getAttribute('data-link'));
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
