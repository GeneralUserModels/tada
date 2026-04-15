import React, { useEffect, useRef, useState } from "react";

type DemoPhase = "idle" | "loading" | "streaming" | "done";

interface TutorialConfig {
  title: string;
  description: string;
  prefill: string;
  streamedText: string;
  placeholder: string;
  hintIdle: string;
  hintDone: string;
}

const TUTORIALS: TutorialConfig[] = [
  {
    title: "Autocomplete",
    description: "Press Option + Tab to complete text from context.",
    prefill: "We tested the model on three benchmarks and found that ",
    streamedText:
      "performance scaled consistently with context length, particularly on long-form summarization tasks. The largest gains appeared when the model had access to at least two prior turns of interaction history.",
    placeholder: "Type some context, then press Option + Tab.",
    hintIdle: "Press Option + Tab to autocomplete.",
    hintDone: "Option + Tab continues from where you left off.",
  },
  {
    title: "You can also prompt it",
    description: "Type a question or instruction, then press Option + Tab.",
    prefill:
      "We tested the model on three benchmarks and found that performance scaled consistently with context length, particularly on long-form summarization tasks. The largest gains appeared when the model had access to at least two prior turns of interaction history.\n\nrewrite this to be more concise-\n\n",
    streamedText:
      "Model performance improved with longer context, especially for summarization, with the strongest gains emerging after two or more prior turns.",
    placeholder: "Write a prompt, then press Option + Tab.",
    hintIdle: "Press Option + Tab to get a response.",
    hintDone: "Tabracadabra responds to instructions too, not just autocomplete.",
  },
];

type Props = {
  onBack: () => void;
  onContinue: () => void;
};

export function TabracadabraStep({ onBack, onContinue }: Props) {
  const SPINNER_FRAMES = ["|", "/", "-", "\\"];
  const SPINNER_TICK_MS = 120;
  const SPINNER_PROGRESS_DURATION_MS = 9000;
  const FAKE_TTFT_MS = 2000;
  const STREAM_TICK_MS = 24;

  const [tutorialStep, setTutorialStep] = useState(0);
  const [text, setText] = useState(TUTORIALS[0].prefill);
  const [phase, setPhase] = useState<DemoPhase>("idle");

  const spinnerTimerRef = useRef<number | null>(null);
  const streamTimerRef = useRef<number | null>(null);
  const loadingDelayTimerRef = useRef<number | null>(null);
  const loadingStartedAtRef = useRef<number | null>(null);
  const baseTextRef = useRef(TUTORIALS[0].prefill);

  const tutorial = TUTORIALS[tutorialStep];

  const stopDemo = () => {
    loadingStartedAtRef.current = null;
    if (spinnerTimerRef.current !== null) {
      window.clearInterval(spinnerTimerRef.current);
      spinnerTimerRef.current = null;
    }
    if (loadingDelayTimerRef.current !== null) {
      window.clearTimeout(loadingDelayTimerRef.current);
      loadingDelayTimerRef.current = null;
    }
    if (streamTimerRef.current !== null) {
      window.clearInterval(streamTimerRef.current);
      streamTimerRef.current = null;
    }
  };

  useEffect(() => {
    return () => {
      stopDemo();
    };
  }, []);

  useEffect(() => {
    stopDemo();
    const t = TUTORIALS[tutorialStep];
    setText(t.prefill);
    baseTextRef.current = t.prefill;
    setPhase("idle");
  }, [tutorialStep]);

  const handleBack = () => {
    if (tutorialStep > 0) {
      setTutorialStep(tutorialStep - 1);
    } else {
      onBack();
    }
  };

  const handleNext = () => {
    if (tutorialStep < TUTORIALS.length - 1) {
      setTutorialStep(tutorialStep + 1);
    } else {
      onContinue();
    }
  };

  return (
    <div className="page active">
      <div className="page-icon">
        <svg width="22" height="22" viewBox="0 0 16 16" fill="none"><path d="M3 4.5h10M3 8h10M3 11.5h7" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/><path d="M11.2 10.7 13.5 8.4l-2.3-2.3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/></svg>
      </div>
      <div className="page-title">{tutorial.title}</div>
      <p className="page-desc">{tutorial.description}</p>
      <p className="page-desc" style={{ fontSize: "12px", opacity: 0.5, marginTop: -4 }}>
        {tutorialStep + 1} of {TUTORIALS.length}
      </p>
      <div className="glass-card">
        <div className="field">
          <span className="field-label">Practice prompt</span>
          <textarea
            className="tutorial-box"
            value={text}
            rows={8}
            onChange={(e) => {
              stopDemo();
              setText(e.target.value);
              setPhase("idle");
              baseTextRef.current = e.target.value;
            }}
            onMouseDown={() => {
              if (phase === "loading" || phase === "streaming") {
                stopDemo();
                setPhase("done");
              }
            }}
            onKeyDown={(e) => {
              if (!(e.key === "Tab" && e.altKey)) {
                if (phase === "loading" || phase === "streaming") {
                  stopDemo();
                  setPhase("done");
                }
                return;
              }
              e.preventDefault();
              if (phase === "loading" || phase === "streaming") return;
              stopDemo();
              baseTextRef.current = text;
              setPhase("loading");
              let spinnerIndex = 0;
              const initialSpinner = `[${SPINNER_FRAMES[spinnerIndex]}] 0%`;
              setText(baseTextRef.current ? `${baseTextRef.current} ${initialSpinner}` : initialSpinner);
              loadingStartedAtRef.current = Date.now();
              spinnerTimerRef.current = window.setInterval(() => {
                spinnerIndex = (spinnerIndex + 1) % SPINNER_FRAMES.length;
                const base = baseTextRef.current;
                const startedAt = loadingStartedAtRef.current;
                const elapsedMs = startedAt ? Date.now() - startedAt : 0;
                const pct = Math.min(100, Math.floor((elapsedMs / SPINNER_PROGRESS_DURATION_MS) * 100));
                const spinner = `[${SPINNER_FRAMES[spinnerIndex]}] ${pct}%`;
                setText(base ? `${base} ${spinner}` : spinner);
              }, SPINNER_TICK_MS);
              loadingDelayTimerRef.current = window.setTimeout(() => {
                let cursor = 0;
                const base = baseTextRef.current;
                const prefix = base ? `${base} ` : "";
                const { streamedText } = tutorial;
                const charsPerTick = Math.max(1, Math.ceil(streamedText.length / 70));
                if (spinnerTimerRef.current !== null) {
                  window.clearInterval(spinnerTimerRef.current);
                  spinnerTimerRef.current = null;
                }
                setPhase("streaming");
                setText(prefix);
                streamTimerRef.current = window.setInterval(() => {
                  cursor = Math.min(cursor + charsPerTick, streamedText.length);
                  setText(`${prefix}${streamedText.slice(0, cursor)}`);
                  if (cursor >= streamedText.length) {
                    stopDemo();
                    baseTextRef.current = `${prefix}${streamedText}`;
                    setPhase("done");
                  }
                }, STREAM_TICK_MS);
              }, FAKE_TTFT_MS);
            }}
            placeholder={tutorial.placeholder}
            aria-label="Tabracadabra tutorial textbox"
          />
          <span className={`field-hint tutorial-hint${phase === "done" ? " done" : ""}`}>
            {phase === "loading" && "Loading... Spinner runs until first tokens arrive."}
            {phase === "streaming" && "Streaming suggestion..."}
            {phase === "idle" && tutorial.hintIdle}
            {phase === "done" && tutorial.hintDone}
          </span>
        </div>
      </div>
      <div className="btn-row">
        <button className="btn btn-ghost" onClick={handleBack}>Back</button>
        <button className="btn btn-primary" onClick={handleNext}>
          {tutorialStep < TUTORIALS.length - 1 ? "Next" : "Finish Setup"}
        </button>
      </div>
    </div>
  );
}
