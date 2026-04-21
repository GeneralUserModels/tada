import React, { useEffect, useRef, useState } from "react";
import { getServerUrl } from "../../../api/client";

type DemoPhase = "idle" | "loading" | "streaming" | "done";

interface TutorialConfig {
  title: string;
  description: string;
  prefill: string;
  placeholder: string;
  hintIdle: string;
  hintDone: string;
}

const TUTORIALS: TutorialConfig[] = [
  {
    title: "Autocomplete",
    description: "Press Option + Tab to complete text from context.",
    prefill: "We tested the model on three benchmarks and found that ",
    placeholder: "Type some context, then press Option + Tab.",
    hintIdle: "Press Option + Tab to autocomplete.",
    hintDone: "Option + Tab continues from where you left off.",
  },
  {
    title: "You can also prompt it",
    description: "Type a question or instruction, then press Option + Tab.",
    prefill:
      "We tested the model on three benchmarks and found that performance scaled consistently with context length, particularly on long-form summarization tasks. The largest gains appeared when the model had access to at least two prior turns of interaction history.\n\nplz emojify this text\n\n",
    placeholder: "Write a prompt, then press Option + Tab.",
    hintIdle: "Press Option + Tab to get a response.",
    hintDone: "Tabracadabra responds to instructions too, not just autocomplete.",
  },
];

const SPINNER_FRAMES = ["|", "/", "-", "\\"];
const SPINNER_TICK_MS = 120;
const SPINNER_PROGRESS_DURATION_MS = 9000;

async function* streamCompletion(text: string, signal: AbortSignal) {
  const res = await fetch(`${getServerUrl()}/api/completions/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
    signal,
  });
  if (!res.ok) throw new Error(`${res.status}`);
  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    yield decoder.decode(value, { stream: true });
  }
}

type Props = {
  onBack: () => void;
  onContinue: () => void;
  isFinal?: boolean;
};

export function TabracadabraStep({ onBack, onContinue, isFinal = true }: Props) {
  const [tutorialStep, setTutorialStep] = useState(0);
  const [text, setText] = useState(TUTORIALS[0].prefill);
  const [phase, setPhase] = useState<DemoPhase>("idle");

  const spinnerTimerRef = useRef<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const loadingStartedAtRef = useRef<number | null>(null);
  const baseTextRef = useRef(TUTORIALS[0].prefill);
  const cancelledRef = useRef(false);

  const tutorial = TUTORIALS[tutorialStep];

  const stopDemo = () => {
    loadingStartedAtRef.current = null;
    cancelledRef.current = true;
    if (spinnerTimerRef.current !== null) {
      window.clearInterval(spinnerTimerRef.current);
      spinnerTimerRef.current = null;
    }
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
  };

  useEffect(() => {
    return () => { stopDemo(); };
  }, []);

  useEffect(() => {
    stopDemo();
    const t = TUTORIALS[tutorialStep];
    setText(t.prefill);
    baseTextRef.current = t.prefill;
    setPhase("idle");
  }, [tutorialStep]);

  const startSpinner = () => {
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
  };

  const stopSpinner = () => {
    loadingStartedAtRef.current = null;
    if (spinnerTimerRef.current !== null) {
      window.clearInterval(spinnerTimerRef.current);
      spinnerTimerRef.current = null;
    }
  };

  const runCompletion = async () => {
    const base = baseTextRef.current;
    const prefix = base ? `${base} ` : "";
    const controller = new AbortController();
    abortRef.current = controller;
    cancelledRef.current = false;

    try {
      let accumulated = "";
      let firstChunk = true;
      for await (const chunk of streamCompletion(base, controller.signal)) {
        if (cancelledRef.current) return;
        if (firstChunk) {
          firstChunk = false;
          stopSpinner();
          setPhase("streaming");
        }
        accumulated += chunk;
        setText(`${prefix}${accumulated}`);
      }
      if (!cancelledRef.current) {
        baseTextRef.current = `${prefix}${accumulated}`;
        setPhase("done");
      }
    } catch {
      if (cancelledRef.current) return;
      stopSpinner();
      setText(base);
      setPhase("idle");
    }
  };

  const handleOptionTab = () => {
    if (phase === "loading" || phase === "streaming") return;
    stopDemo();
    baseTextRef.current = text;
    cancelledRef.current = false;
    setPhase("loading");
    startSpinner();
    runCompletion();
  };

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
              handleOptionTab();
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
          {tutorialStep < TUTORIALS.length - 1 ? "Next" : isFinal ? "Finish Setup" : "Next"}
        </button>
      </div>
    </div>
  );
}
