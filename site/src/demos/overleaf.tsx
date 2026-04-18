import type { Demo } from "./types";

function OverleafChrome() {
  return (
    <div className="chrome-overleaf">
      <div className="chrome-toolbar">
        <button className="chrome-tb-btn active">Source</button>
        <button className="chrome-tb-btn">Rich Text</button>
        <div className="chrome-tb-sep" />
        <button className="chrome-tb-btn icon">B</button>
        <button className="chrome-tb-btn icon">I</button>
        <button className="chrome-tb-btn icon">U</button>
        <div className="chrome-tb-sep" />
        <button className="chrome-tb-btn icon">∑</button>
        <button className="chrome-tb-btn icon">🔗</button>
      </div>
    </div>
  );
}

export const overleafDemo: Demo = {
  steps: [
    {
      kind: "user",
      text: "What's the cold-start limitation with tabracadabra?\n",
    },
    {
      kind: "assistant",
      trigger: "autocomplete",
      text: "Tabracadabra performs best when it has a warm context window with enough prior interaction to infer user intent and style. In true cold-start settings, brand-new users often provide too little historical signal for the model to ground its suggestions reliably. As a result, early completions can be less personalized, less stable, and occasionally lower quality than what we see after a short period of use. This gap narrows as the interaction history grows and the system accumulates richer context.\n",
    },
    {
      kind: "user",
      text: "\nturn that into a paper sentence for limitations\n",
    },
    {
      kind: "assistant",
      trigger: "prompt",
      text: "A key limitation of our approach is its reliance on a warm context window, which may reduce effectiveness in cold-start settings where user history is minimal.",
    },
    {
      kind: "delete",
      count: 53,
    },
    {
      kind: "assistant",
      trigger: "autocomplete",
      text: "for users with sparse history.",
    },
  ],
  theme: {
    app: "Overleaf",
    icon: "📄",
    fontFamily: "'Georgia', 'Times New Roman', 'Palatino', serif",
    fontSize: "14px",
    bg: "#fdfbf7",
    headerBg: "linear-gradient(180deg, #f5f0e8 0%, #ece6db 100%)",
    headerText: "#3b3226",
    textColor: "#3b3226",
    cursorColor: "#3b3226",
  },
  topChrome: <OverleafChrome />,
};
