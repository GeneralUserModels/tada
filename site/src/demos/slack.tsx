import type { Demo } from "./types";

function SlackTopChrome() {
  return (
    <div className="chrome-slack-top">
      <span className="chrome-slack-hash">#</span>
      <span className="chrome-slack-channel">powernap-dev</span>
      <span className="chrome-slack-topic">context window & caching</span>
    </div>
  );
}

function SlackBottomChrome() {
  return (
    <div className="chrome-slack-bottom">
      <button className="chrome-slack-action">＋</button>
      <div className="chrome-slack-bottom-right">
        <button className="chrome-slack-action">😊</button>
        <button className="chrome-slack-action">@</button>
        <button className="chrome-slack-action">📎</button>
      </div>
    </div>
  );
}

export const slackDemo: Demo = {
  steps: [
    {
      kind: "user",
      text: "what changed with cache behavior in prod?\n",
    },
    {
      kind: "assistant",
      trigger: "autocomplete",
      text:
        "You should mention that cache misses now trigger a sliding-window retrieval fallback after the threshold is exceeded.\n",
    },
    {
      kind: "user",
      text: "\na draft:\n",
    },
    {
      kind: "assistant",
      trigger: "prompt",
      text:
        "hey team - shipped the context window update.\nmain change: when cache misses cross 15%, retrieval falls back to a sliding window automatically.\nshould be transparent, but let's keep an eye on prod latency today.",
    },
    {
      kind: "user",
      text: "\nelaborate a little + touch on that detail i discussed with Kanishk-\n",
    },
    {
      kind: "assistant",
      trigger: "autocomplete",
      text:
        "also (cc: @Kanishk), the first latency spike we saw came from cold-cache repopulation right after rollout, not sustained query load. if latency stays elevated after warmup, that's when we should investigate.",
    },
    {
      kind: "delete",
      from: "middle",
      matchText:
        "\n\nelaborate a little + touch on that detail i discussed with Kanishk-\n",
      pauseAfter: 760,
    },
  ],
  theme: {
    app: "Slack",
    icon: "💬",
    fontFamily: "'Lato', -apple-system, BlinkMacSystemFont, sans-serif",
    fontSize: "13px",
    bg: "#ffffff",
    headerBg: "linear-gradient(180deg, #3F0E40 0%, #350d36 100%)",
    headerText: "#ffffff",
    textColor: "#1d1c1d",
    cursorColor: "#1264a3",
  },
  topChrome: <SlackTopChrome />,
  bottomChrome: <SlackBottomChrome />,
};
