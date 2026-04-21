import React from "react";
import { SAMPLE_TADA_HTML } from "./tadaSample";

type Props = {
  onBack: () => void;
  onContinue: () => void;
  isFinal?: boolean;
};

export function TadasStep({ onBack, onContinue, isFinal = false }: Props) {
  return (
    <div className="page active" style={{ maxWidth: 480 }}>
      <div className="page-icon">
        <svg width="22" height="22" viewBox="0 0 16 16" fill="none">
          <path d="M8 1.5l1.6 3.4 3.7.5-2.7 2.6.7 3.7L8 9.9 4.7 11.7l.7-3.7L2.7 5.4l3.7-.5L8 1.5z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round"/>
        </svg>
      </div>
      <div className="page-title">Tadas</div>
      <p className="page-desc">
        Proactive, just-in-time mini-apps your assistant builds for you. They run on their own schedule, so the answer is already waiting the moment you need it — no prompt, no asking.
      </p>

      <div className="tadas-meta-card">
        <div className="tadas-meta-title">Yellow Brick Road — Journey Planner</div>
        <div className="tadas-meta-desc">
          Today's route options, party status, and where to commit the next leg — updated each morning based on yesterday's march.
        </div>
        <div className="tadas-meta-schedule">
          <span className="tadas-schedule-chip">daily · at dawn</span>
          <span className="tadas-meta-sep">Next run tomorrow</span>
        </div>
      </div>

      <iframe
        className="tadas-iframe"
        sandbox="allow-scripts allow-popups allow-popups-to-escape-sandbox"
        srcDoc={SAMPLE_TADA_HTML}
        title="Sample tada"
      />

      <p className="tadas-hint">
        Pick a path to commit — the tada remembers your choice and plans tomorrow around it.
      </p>

      <div className="btn-row">
        <button className="btn btn-ghost" onClick={onBack}>Back</button>
        <button className="btn btn-primary" onClick={onContinue}>Next</button>
      </div>
    </div>
  );
}
