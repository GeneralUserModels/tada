import type { Demo } from "./types";

function MailChrome() {
  return (
    <div className="chrome-mail">
      <div className="chrome-mail-field">
        <span className="chrome-mail-label">To:</span>
        <span className="chrome-mail-value">advisors@stanford.edu</span>
      </div>
      <div className="chrome-mail-field">
        <span className="chrome-mail-label">Subject:</span>
        <span className="chrome-mail-value">Re: Paper draft — section 3 framing</span>
      </div>
      <div className="chrome-mail-toolbar">
        <button className="chrome-tb-btn icon">B</button>
        <button className="chrome-tb-btn icon">I</button>
        <button className="chrome-tb-btn icon">U</button>
        <div className="chrome-tb-sep" />
        <button className="chrome-tb-btn icon">🔗</button>
        <button className="chrome-tb-btn icon">📎</button>
      </div>
    </div>
  );
}

export const mailDemo: Demo = {
  steps: [
    {
      kind: "user",
      text: "before i forget: what should i send Diyi and Michael today?\n",
    },
    {
      kind: "assistant",
      trigger: "autocomplete",
      text: "You planned to send them a short follow-up email about the paper timeline before Friday.\n",
    },
    {
      kind: "user",
      text: "\nyep. draft that email\n",
    },
    {
      kind: "assistant",
      trigger: "prompt",
      text:
        "Hi all!\n\nWanted to check in on the paper timeline we discussed last week. If there's a revised schedule for COLM 2026, I'd love to align on next steps this week.\n\nThanks,\nOmar\n",
    },
    {
      kind: "delete",
      from: "start",
      count: 172,
    },
    {
      kind: "user",
      text: "\ntoo wordy. make it warmer + shorter-\n",
    },
    {
      kind: "assistant",
      trigger: "autocomplete",
      text:
        "Hi all!\n\nI think we're chugging along on the COLM deadline as usual, lemme know if you have any thoughts on paper timeline\n\nOmar\n",
    },
  ],
  theme: {
    app: "Mail",
    icon: "✉️",
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Helvetica Neue', sans-serif",
    fontSize: "13px",
    bg: "#ffffff",
    headerBg: "linear-gradient(180deg, #f8f8f8 0%, #ececec 100%)",
    headerText: "#1d1d1f",
    textColor: "#1d1d1f",
    cursorColor: "#007AFF",
  },
  topChrome: <MailChrome />,
};
