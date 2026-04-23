import React from "react";
import { SAMPLE_MEMEX_HTML } from "./memexSample";

type Props = {
  onBack: () => void;
  onContinue: () => void;
};

export function MemexStep({ onBack, onContinue }: Props) {
  return (
    <div className="page active" style={{ maxWidth: 480 }}>
      <div className="page-icon">
        <svg width="22" height="22" viewBox="0 0 16 16" fill="none">
          <circle cx="8" cy="3.5" r="1.5" stroke="currentColor" strokeWidth="1.3"/>
          <circle cx="3.5" cy="8" r="1.5" stroke="currentColor" strokeWidth="1.3"/>
          <circle cx="12.5" cy="8" r="1.5" stroke="currentColor" strokeWidth="1.3"/>
          <circle cx="5.5" cy="13" r="1.5" stroke="currentColor" strokeWidth="1.3"/>
          <circle cx="10.5" cy="13" r="1.5" stroke="currentColor" strokeWidth="1.3"/>
          <path d="M6.5 4.5L5 6.5M9.5 4.5L11 6.5M3.5 9.5L5 11.5M12.5 9.5L11 11.5" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round"/>
        </svg>
      </div>
      <div className="page-title">Memex</div>
      <p className="page-desc">
        A personal wiki of your life — pages for the people, projects, and threads that keep coming up, linked so you can step back in.
      </p>

      <iframe
        className="sample-iframe"
        sandbox="allow-scripts allow-popups allow-popups-to-escape-sandbox"
        srcDoc={SAMPLE_MEMEX_HTML}
        title="Sample Memex"
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
