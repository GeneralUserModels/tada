import { type ReactNode, useEffect, useState } from "react";

const REPO = "GeneralUserModels/powernap";
const RELEASE_URL = `https://github.com/${REPO}/releases/latest`;

const SPINNER_FRAMES = ["◐", "◓", "◑", "◒"];

interface DemoTheme {
  app: string;
  icon: string;
  fontFamily: string;
  fontSize: string;
  bg: string;
  headerBg: string;
  headerText: string;
  textColor: string;
  cursorColor: string;
}

interface Demo {
  typed: string;
  completion: string;
  theme: DemoTheme;
  topChrome: ReactNode;
  bottomChrome?: ReactNode;
}

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

const DEMOS: Demo[] = [
  {
    typed: "The main limitation of our approach is that ",
    completion:
      "it assumes access to a recent context window, which may not generalize well to cold-start scenarios where the user model has limited prior observations.",
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
  },
  {
    typed: "Hey Sarah, thanks for the feedback on the draft. I think we should ",
    completion:
      "revisit the framing in section 3 — the current intro buries the key contribution. Happy to sync tomorrow if you're free.",
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
  },
  {
    typed: "hey team, just pushed the new context window changes. the main thing to note is ",
    completion:
      "that retrieval now falls back to a sliding window when the cache miss rate exceeds 15% — should be transparent but worth watching latency in prod.",
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
  },
];

type Phase = "typing" | "holding" | "spinner" | "streaming" | "done";

function useAutocompleteDemo() {
  const [demoIdx, setDemoIdx] = useState(0);
  const [phase, setPhase] = useState<Phase>("typing");
  const [visibleTyped, setVisibleTyped] = useState("");
  const [spinnerIdx, setSpinnerIdx] = useState(0);
  const [spinnerPct, setSpinnerPct] = useState(0);
  const [visibleCompletion, setVisibleCompletion] = useState("");

  const demo = DEMOS[demoIdx];

  useEffect(() => {
    let timeout: ReturnType<typeof setTimeout>;
    let frame = 0;

    function reset() {
      setVisibleTyped("");
      setVisibleCompletion("");
      setSpinnerIdx(0);
      setSpinnerPct(0);
      setPhase("typing");
      frame = 0;
    }

    if (phase === "typing") {
      const typeSpeed = 30;
      function typeNext() {
        if (frame < demo.typed.length) {
          frame++;
          setVisibleTyped(demo.typed.slice(0, frame));
          timeout = setTimeout(typeNext, typeSpeed);
        } else {
          timeout = setTimeout(() => setPhase("holding"), 400);
        }
      }
      typeNext();
    } else if (phase === "holding") {
      timeout = setTimeout(() => setPhase("spinner"), 600);
    } else if (phase === "spinner") {
      let tick = 0;
      const totalTicks = 18;
      function spinNext() {
        if (tick < totalTicks) {
          setSpinnerIdx(tick % SPINNER_FRAMES.length);
          setSpinnerPct(
            Math.min(100, Math.round(((tick + 1) / totalTicks) * 100))
          );
          tick++;
          timeout = setTimeout(spinNext, 120);
        } else {
          setPhase("streaming");
        }
      }
      spinNext();
    } else if (phase === "streaming") {
      frame = 0;
      const streamSpeed = 18;
      function streamNext() {
        if (frame < demo.completion.length) {
          frame++;
          setVisibleCompletion(demo.completion.slice(0, frame));
          timeout = setTimeout(streamNext, streamSpeed);
        } else {
          timeout = setTimeout(() => setPhase("done"), 2000);
        }
      }
      streamNext();
    } else if (phase === "done") {
      timeout = setTimeout(() => {
        setDemoIdx((i) => (i + 1) % DEMOS.length);
        reset();
      }, 600);
    }

    return () => clearTimeout(timeout);
  }, [phase, demo]);

  const spinnerText =
    phase === "spinner"
      ? `${SPINNER_FRAMES[spinnerIdx]} ${spinnerPct.toString().padStart(3, " ")}%`
      : "";

  return { demoIdx, visibleTyped, visibleCompletion, spinnerText, phase };
}

export function App() {
  const { demoIdx, visibleTyped, visibleCompletion, spinnerText, phase } =
    useAutocompleteDemo();

  const demo = DEMOS[demoIdx];
  const theme = demo.theme;

  const demoStyle = {
    "--demo-bg": theme.bg,
    "--demo-header-bg": theme.headerBg,
    "--demo-header-text": theme.headerText,
    "--demo-text": theme.textColor,
    "--demo-cursor": theme.cursorColor,
    "--demo-font": theme.fontFamily,
    "--demo-font-size": theme.fontSize,
  } as React.CSSProperties;

  return (
    <div className="page">
      <div className="grain" />

      <main className="hero">
        <h1 className="hero-title">
          Tabracadabra{" "}
          <span className="hero-emoji" aria-hidden="true">
            🎩
          </span>
        </h1>
        <p className="hero-subtitle">
          Hold Tab in any textbox. Get a streaming autocomplete powered by a
          model that knows your context.
        </p>

        <div className="hero-actions">
          <a href={RELEASE_URL} className="btn btn-primary">
            <DownloadIcon />
            Download for macOS
          </a>
          <a href={`https://github.com/${REPO}`} className="btn btn-secondary">
            <StarIcon />
            Star on GitHub
          </a>
        </div>
      </main>

      <div className="demo-container">
        <div className="demo" style={demoStyle}>
          <div className="demo-header">
            <div className="demo-dots">
              <span />
              <span />
              <span />
            </div>
            <div className="demo-app-label">
              <span className="demo-app-icon">{theme.icon}</span>
              {theme.app}
            </div>
            <div className="demo-tab-hint">
              {(phase === "holding" || phase === "spinner") && (
                <span className="tab-key-badge">
                  Tab
                  <span className="tab-key-held" />
                </span>
              )}
            </div>
          </div>

          {demo.topChrome}

          <div className="demo-body">
            <span className="demo-typed">{visibleTyped}</span>
            {phase === "spinner" && (
              <span className="demo-spinner">{spinnerText}</span>
            )}
            {(phase === "streaming" || phase === "done") && (
              <span className="demo-completion">{visibleCompletion}</span>
            )}
            {phase !== "done" && <span className="demo-cursor" />}
          </div>

          {demo.bottomChrome}
        </div>
      </div>

    </div>
  );
}

function StarIcon() {
  return (
    <svg
      width="15"
      height="15"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
    </svg>
  );
}

function DownloadIcon() {
  return (
    <svg
      width="15"
      height="15"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="7 10 12 15 17 10" />
      <line x1="12" y1="15" x2="12" y2="3" />
    </svg>
  );
}
