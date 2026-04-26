export interface ChatSampleConfig {
  sessionTitle: string;
  userPrompt: string;
  assistantHtml: string;
}

export function buildChatSampleHtml(cfg: ChatSampleConfig): string {
  const safeTitle = escapeHtml(cfg.sessionTitle);
  const userJson = JSON.stringify(cfg.userPrompt);
  const assistantJson = JSON.stringify(cfg.assistantHtml);
  return BASE_TEMPLATE
    .replace("__SESSION_TITLE__", safeTitle)
    .replace("__USER_JSON__", userJson)
    .replace("__ASSISTANT_JSON__", assistantJson);
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

const BASE_TEMPLATE = `<!doctype html>
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
    --paper-strong: rgba(255,255,255,0.78);
    --text: #2C3A28;
    --text-secondary: #6B7A65;
    --text-tertiary: #9BA896;
    --border: rgba(132,177,121,0.22);
    --sage-soft: rgba(132,177,121,0.14);
    --sage-strong: rgba(132,177,121,0.30);
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
    line-height: 1.45;
    -webkit-font-smoothing: antialiased;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    height: 100%;
  }

  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    padding: 8px 12px 7px;
    border-bottom: 1px solid var(--border);
  }
  .head-title {
    font-size: 11px;
    font-weight: 660;
    letter-spacing: -0.1px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .head-meta {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-shrink: 0;
  }
  .badge {
    font-size: 8.5px;
    font-weight: 600;
    padding: 1.5px 6px;
    border-radius: 99px;
    background: var(--sage-soft);
    color: var(--sage);
    white-space: nowrap;
  }
  .effort {
    font-size: 8.5px;
    font-weight: 600;
    padding: 1.5px 6px;
    border-radius: 99px;
    background: rgba(185,136,56,0.14);
    color: var(--amber);
    border: 1px solid rgba(185,136,56,0.20);
  }

  .messages {
    flex: 1;
    overflow-y: auto;
    padding: 12px 14px 8px;
    display: flex;
    flex-direction: column;
    gap: 9px;
  }
  .messages::-webkit-scrollbar { width: 4px; }
  .messages::-webkit-scrollbar-thumb { background: var(--sage-soft); border-radius: 2px; }

  .msg {
    display: flex;
    animation: fadeUp 0.4s ease;
  }
  @keyframes fadeUp {
    from { opacity: 0; transform: translateY(4px); }
    to { opacity: 1; transform: translateY(0); }
  }
  .msg.user { justify-content: flex-end; }
  .bubble {
    max-width: 86%;
    padding: 8px 11px;
    border-radius: 12px;
    font-size: 10.5px;
    line-height: 1.5;
    white-space: pre-wrap;
    word-wrap: break-word;
  }
  .msg.user .bubble {
    background: var(--sage-soft);
    color: var(--text);
    border: 1px solid var(--border);
    border-bottom-right-radius: 4px;
  }
  .msg.assistant .bubble {
    background: var(--paper-strong);
    color: var(--text);
    border: 1px solid var(--border);
    border-bottom-left-radius: 4px;
    backdrop-filter: blur(8px);
  }
  .bubble strong { font-weight: 660; }
  .bubble em { color: var(--amber); font-style: normal; font-weight: 600; }
  .bubble .row {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 8px;
    margin-top: 8px;
    margin-bottom: 1px;
  }
  .bubble .row:first-child { margin-top: 0; }
  .bubble .row .who { font-weight: 660; }
  .bubble .row .when { font-size: 9.5px; color: var(--text-tertiary); }
  .bubble .body { color: var(--text-secondary); }
  .bubble ul { margin: 4px 0 4px 14px; padding: 0; }
  .bubble li { margin: 2px 0; color: var(--text-secondary); }
  .bubble .footer {
    margin-top: 9px;
    padding-top: 7px;
    border-top: 1px solid var(--border);
    font-size: 9.5px;
    color: var(--text-tertiary);
  }
  .cursor {
    display: inline-block;
    width: 1.5px;
    height: 11px;
    background: var(--sage);
    vertical-align: text-bottom;
    margin-left: 1px;
    animation: blink 1s step-end infinite;
  }
  @keyframes blink { 50% { opacity: 0; } }

  .typing {
    display: inline-flex;
    gap: 3px;
    padding: 2px 0;
  }
  .typing span {
    width: 5px;
    height: 5px;
    border-radius: 50%;
    background: var(--sage);
    opacity: 0.5;
    animation: typingPulse 1.1s infinite ease-in-out;
  }
  .typing span:nth-child(2) { animation-delay: 0.15s; }
  .typing span:nth-child(3) { animation-delay: 0.3s; }
  @keyframes typingPulse {
    0%, 80%, 100% { opacity: 0.3; transform: scale(0.85); }
    40% { opacity: 1; transform: scale(1); }
  }

  footer {
    border-top: 1px solid var(--border);
    padding: 8px 10px;
    display: flex;
    align-items: center;
    gap: 6px;
    background: rgba(255,255,255,0.35);
  }
  .input {
    flex: 1;
    background: var(--paper);
    border: 1px solid var(--border);
    border-radius: 99px;
    padding: 5px 11px;
    font-size: 10px;
    color: var(--text-tertiary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .send {
    font-size: 9.5px;
    font-weight: 650;
    color: var(--sage);
    background: var(--sage-soft);
    border: 1px solid var(--border);
    border-radius: 99px;
    padding: 4px 11px;
    flex-shrink: 0;
  }
</style>
</head>
<body>
  <header>
    <div class="head-title">__SESSION_TITLE__</div>
    <div class="head-meta">
      <span class="badge">opus</span>
      <span class="effort">Medium</span>
    </div>
  </header>
  <div class="messages" id="msgs"></div>
  <footer>
    <div class="input">Ask anything…</div>
    <div class="send">Send</div>
  </footer>

<script>
(function() {
  const msgs = document.getElementById('msgs');
  const USER_TEXT = __USER_JSON__;
  const ASSISTANT_HTML = __ASSISTANT_JSON__;

  function addMsg(role, html) {
    const wrap = document.createElement('div');
    wrap.className = 'msg ' + role;
    const bubble = document.createElement('div');
    bubble.className = 'bubble';
    bubble.innerHTML = html;
    wrap.appendChild(bubble);
    msgs.appendChild(wrap);
    msgs.scrollTop = msgs.scrollHeight;
    return bubble;
  }

  function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

  async function typeUser(bubble, text) {
    bubble.textContent = '';
    for (let i = 0; i < text.length; i++) {
      bubble.textContent = text.slice(0, i + 1);
      msgs.scrollTop = msgs.scrollHeight;
      await sleep(28);
    }
  }

  async function streamHtml(bubble, html) {
    bubble.innerHTML = '<span class="cursor"></span>';
    const STEP = 3;
    const TICK = 32;
    let i = 0;
    while (i < html.length) {
      let next = Math.min(i + STEP, html.length);
      // Don't split inside an HTML tag.
      const slice = html.slice(0, next);
      const lastOpen = slice.lastIndexOf('<');
      const lastClose = slice.lastIndexOf('>');
      if (lastOpen > lastClose) {
        const close = html.indexOf('>', next);
        if (close !== -1) next = close + 1;
      }
      bubble.innerHTML = html.slice(0, next) + '<span class="cursor"></span>';
      msgs.scrollTop = msgs.scrollHeight;
      i = next;
      await sleep(TICK);
    }
    bubble.innerHTML = html;
    msgs.scrollTop = msgs.scrollHeight;
  }

  async function play() {
    await sleep(700);
    const userBubble = addMsg('user', '');
    await typeUser(userBubble, USER_TEXT);
    await sleep(800);
    const thinking = addMsg('assistant', '<div class="typing"><span></span><span></span><span></span></div>');
    await sleep(1500);
    await streamHtml(thinking, ASSISTANT_HTML);
  }

  play();
})();
</script>
</body>
</html>`;
