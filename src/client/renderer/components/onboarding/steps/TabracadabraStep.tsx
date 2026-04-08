import React, { useEffect, useRef, useState } from "react";

type DemoPhase = "idle" | "holding" | "loading" | "streaming" | "done";

type Props = {
  onBack: () => void;
  onContinue: () => void;
};

export function TabracadabraStep({ onBack, onContinue }: Props) {
  const HOLD_THRESHOLD_MS = 350;
  const SPINNER_FRAMES = ["◐", "◓", "◑", "◒"];
  const SPINNER_TICK_MS = 120;
  const SPINNER_PROGRESS_DURATION_MS = 9000;
  const FAKE_TTFT_MS = 2000;
  const STREAM_TICK_MS = 24;

  const [text, setText] = useState("");
  const [phase, setPhase] = useState<DemoPhase>("idle");

  const activationTimerRef = useRef<number | null>(null);
  const spinnerTimerRef = useRef<number | null>(null);
  const streamTimerRef = useRef<number | null>(null);
  const loadingDelayTimerRef = useRef<number | null>(null);
  const tabDownRef = useRef(false);
  const activatedRef = useRef(false);
  const loadingStartedAtRef = useRef<number | null>(null);
  const baseTextRef = useRef("");

  const stopDemo = () => {
    tabDownRef.current = false;
    activatedRef.current = false;
    loadingStartedAtRef.current = null;
    if (activationTimerRef.current !== null) {
      window.clearTimeout(activationTimerRef.current);
      activationTimerRef.current = null;
    }
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
      <p className="page-desc">Try the demo text box and press Tab. This is a fake stream to mimic the real Tabracadabra feel.</p>
      <div className="glass-card">
        <div className="field">
          <span className="field-label">Practice prompt</span>
          <textarea
            className="tutorial-box"
            value={text}
            rows={6}
            onChange={(e) => {
              stopDemo();
              setText(e.target.value);
              setPhase("idle");
              baseTextRef.current = e.target.value;
            }}
            onKeyDown={(e) => {
              if (e.key !== "Tab") {
                if (phase === "loading" || phase === "streaming") {
                  stopDemo();
                  setPhase("done");
                }
                return;
              }
              const streamedParagraph = "Great work! This is placeholder text for now, but once you're done with onboarding, it'll complete from everything you've seen. You can also use this to ask an LLM questions in any text box! Just have a question right before, tab, and get the answer...";
              e.preventDefault();
              if (phase === "loading" || phase === "streaming" || tabDownRef.current) return;
              stopDemo();
              baseTextRef.current = text;
              tabDownRef.current = true;
              activatedRef.current = false;
              setPhase("holding");
              let spinnerIndex = 0;
              setText(baseTextRef.current ? `${baseTextRef.current} ${SPINNER_FRAMES[spinnerIndex]}` : SPINNER_FRAMES[spinnerIndex]);
              spinnerTimerRef.current = window.setInterval(() => {
                spinnerIndex = (spinnerIndex + 1) % SPINNER_FRAMES.length;
                const base = baseTextRef.current;
                if (!activatedRef.current) {
                  setText(base ? `${base} ${SPINNER_FRAMES[spinnerIndex]}` : SPINNER_FRAMES[spinnerIndex]);
                  return;
                }
                const startedAt = loadingStartedAtRef.current;
                const elapsedMs = startedAt ? Date.now() - startedAt : 0;
                const pct = Math.min(100, Math.floor((elapsedMs / SPINNER_PROGRESS_DURATION_MS) * 100));
                const spinner = `${SPINNER_FRAMES[spinnerIndex]} ${String(pct).padStart(3, " ")}%`;
                setText(base ? `${base} ${spinner}` : spinner);
              }, SPINNER_TICK_MS);
              activationTimerRef.current = window.setTimeout(() => {
                if (!tabDownRef.current) return;
                activatedRef.current = true;
                loadingStartedAtRef.current = Date.now();
                setPhase("loading");
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
              }, HOLD_THRESHOLD_MS);
            }}
            onKeyUp={(e) => {
              if (e.key !== "Tab") return;
              e.preventDefault();
              const wasActivated = activatedRef.current;
              tabDownRef.current = false;
              if (!wasActivated) {
                stopDemo();
                setText(baseTextRef.current);
                setPhase("idle");
              }
            }}
            placeholder="Type a start here, then press Tab..."
            aria-label="Tabracadabra tutorial textbox"
          />
          <span className={`field-hint tutorial-hint${phase === "done" ? " done" : ""}`}>
            {(phase === "holding" || phase === "loading") && "Listening for hold..."}
            {phase === "streaming" && "Streaming suggestion..."}
            {phase === "idle" && "Hold Tab (not tap) to trigger fake autocomplete."}
            {phase === "done" && "Done. Fake local stream preview."}
          </span>
        </div>
      </div>
      <div className="btn-row">
        <button className="btn btn-ghost" onClick={onBack}>Back</button>
        <button className="btn btn-primary" onClick={onContinue}>Continue</button>
      </div>
    </div>
  );
}
