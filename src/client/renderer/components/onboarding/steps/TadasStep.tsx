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
        Proactive mini-apps that run on their own schedule — answers waiting before you need to ask.
      </p>

      <iframe
        className="sample-iframe"
        sandbox="allow-scripts allow-popups allow-popups-to-escape-sandbox"
        srcDoc={SAMPLE_TADA_HTML}
        title="Sample tada"
      />

      <p className="sample-hint">
        Four tabs of what Dorothy knows about Oz — assembled fresh each dawn.
      </p>

      <div className="btn-row">
        <button className="btn btn-ghost" onClick={onBack}>Back</button>
        <button className="btn btn-primary" onClick={onContinue}>Next</button>
      </div>
    </div>
  );
}
