import React, { useEffect, useRef, useState } from "react";

type DemoPhase = "idle" | "loading" | "streaming" | "done";

type Props = {
  onBack: () => void;
  onContinue: () => void;
};

export function TabracadabraStep({ onBack, onContinue }: Props) {
  const SPINNER_FRAMES = ["◐", "◓", "◑", "◒"];
  const SPINNER_TICK_MS = 120;
  const SPINNER_PROGRESS_DURATION_MS = 9000;
  const FAKE_TTFT_MS = 2000;
  const STREAM_TICK_MS = 24;

  const [text, setText] = useState("");
  const [phase, setPhase] = useState<DemoPhase>("idle");

  const spinnerTimerRef = useRef<number | null>(null);
  const streamTimerRef = useRef<number | null>(null);
  const loadingDelayTimerRef = useRef<number | null>(null);
  const loadingStartedAtRef = useRef<number | null>(null);
  const baseTextRef = useRef("");

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

  return (
    <div className="page active">
      <div className="page-icon">
        <svg width="22" height="22" viewBox="0 0 16 16" fill="none"><path d="M3 4.5h10M3 8h10M3 11.5h7" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/><path d="M11.2 10.7 13.5 8.4l-2.3-2.3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/></svg>
      </div>
      <div className="page-title">Learning Tabracadabra</div>
      <p className="page-desc">In the text box below, focus and press Option + Tab.</p>
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
              const streamedParagraph = "Great work! Once onboarding is complete, Tabracadabra can complete text based on your context.\n\nIn any text field (Google Docs, notes, chat boxes, etc.), press Option + Tab to start generation. A spinner appears while the model is thinking, then text streams in. If you type or click, generation stops immediately and keeps whatever has already been inserted.";
              e.preventDefault();
              if (phase === "loading" || phase === "streaming") return;
              stopDemo();
              baseTextRef.current = text;
              setPhase("loading");
              let spinnerIndex = 0;
              setText(baseTextRef.current ? `${baseTextRef.current} ${SPINNER_FRAMES[spinnerIndex]}` : SPINNER_FRAMES[spinnerIndex]);
              loadingStartedAtRef.current = Date.now();
              spinnerTimerRef.current = window.setInterval(() => {
                spinnerIndex = (spinnerIndex + 1) % SPINNER_FRAMES.length;
                const base = baseTextRef.current;
                const startedAt = loadingStartedAtRef.current;
                const elapsedMs = startedAt ? Date.now() - startedAt : 0;
                const pct = Math.min(100, Math.floor((elapsedMs / SPINNER_PROGRESS_DURATION_MS) * 100));
                const spinner = `${SPINNER_FRAMES[spinnerIndex]} ${String(pct).padStart(3, " ")}%`;
                setText(base ? `${base} ${spinner}` : spinner);
              }, SPINNER_TICK_MS);
              loadingDelayTimerRef.current = window.setTimeout(() => {
                let cursor = 0;
                const base = baseTextRef.current;
                const prefix = base ? `${base} ` : "";
                const charsPerTick = Math.max(1, Math.ceil(streamedParagraph.length / 70));
                if (spinnerTimerRef.current !== null) {
                  window.clearInterval(spinnerTimerRef.current);
                  spinnerTimerRef.current = null;
                }
                setPhase("streaming");
                setText(prefix);
                streamTimerRef.current = window.setInterval(() => {
                  cursor = Math.min(cursor + charsPerTick, streamedParagraph.length);
                  setText(`${prefix}${streamedParagraph.slice(0, cursor)}`);
                  if (cursor >= streamedParagraph.length) {
                    stopDemo();
                    baseTextRef.current = `${prefix}${streamedParagraph}`;
                    setPhase("done");
                  }
                }, STREAM_TICK_MS);
              }, FAKE_TTFT_MS);
            }}
            placeholder="Focus on this textbox and press Option + Tab."
            aria-label="Tabracadabra tutorial textbox"
          />
          <span className={`field-hint tutorial-hint${phase === "done" ? " done" : ""}`}>
            {phase === "loading" && "Loading... Spinner runs until first tokens arrive."}
            {phase === "streaming" && "Streaming suggestion..."}
            {phase === "idle" && "Press Option + Tab to trigger autocomplete."}
            {phase === "done" && "Done. Option + Tab starts, typing or clicking cancels."}
          </span>
        </div>
      </div>
      <div className="btn-row">
        <button className="btn btn-ghost" onClick={onBack}>Back</button>
        <button className="btn btn-primary" onClick={onContinue}>Finish Setup</button>
      </div>
    </div>
  );
}
