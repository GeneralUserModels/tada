import React from "react";
import { SAMPLE_PENSIEVE_HTML } from "./pensieveSample";

type Props = {
  onBack: () => void;
  onContinue: () => void;
};

export function PensieveStep({ onBack, onContinue }: Props) {
  return (
    <div className="page active" style={{ maxWidth: 480 }}>
      <div className="page-icon">
        <svg width="22" height="22" viewBox="0 0 16 16" fill="none">
          <path d="M3 2h7l3 3v9H3V2z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round"/>
          <path d="M10 2v3h3" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round"/>
          <path d="M5 8h6M5 10.5h6M5 13h4" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round"/>
        </svg>
      </div>
      <div className="page-title">Pensieve</div>
      <p className="page-desc">
        Like the Pensieve in Harry Potter — a wiki of your life, pages for the people, projects, and threads that keep coming up, linked so you can step back in.
      </p>

      <iframe
        className="sample-iframe"
        sandbox="allow-scripts allow-popups allow-popups-to-escape-sandbox"
        srcDoc={SAMPLE_PENSIEVE_HTML}
        title="Sample Pensieve"
      />

      <p className="sample-hint">
        Click a tile to open its page — wiki-links keep the threads tied together.
      </p>

      <div className="btn-row">
        <button className="btn btn-ghost" onClick={onBack}>Back</button>
        <button className="btn btn-primary" onClick={onContinue}>Finish Setup</button>
      </div>
    </div>
  );
}
