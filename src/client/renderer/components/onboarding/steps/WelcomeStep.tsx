import React from "react";

type Props = {
  onStart: () => void;
};

export function WelcomeStep({ onStart }: Props) {
  return (
    <div className="page active">
      <div className="welcome-brand">
        <svg width="28" height="28" viewBox="0 0 20 20" fill="none">
          <text x="1" y="17" fontFamily="sans-serif" fontWeight="bold" fontSize="11" fill="url(#bGrad)">Z</text>
          <text x="7" y="13" fontFamily="sans-serif" fontWeight="bold" fontSize="8" fill="url(#bGrad)" opacity="0.75">z</text>
          <text x="12" y="9" fontFamily="sans-serif" fontWeight="bold" fontSize="6" fill="url(#bGrad)" opacity="0.5">z</text>
          <defs>
            <linearGradient id="bGrad" x1="2" y1="2" x2="18" y2="18">
              <stop stopColor="#84B179"/><stop offset="1" stopColor="#A2CB8B"/>
            </linearGradient>
          </defs>
        </svg>
        <span>Tada</span>
      </div>
      <p className="welcome-subtitle">A few quick steps to get you up and running. This only takes a minute.</p>
      <div className="glass-card">
        <div className="welcome-features">
          <div className="welcome-feature">
            <div className="wf-icon">
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><rect x="2" y="3" width="12" height="10" rx="2" stroke="currentColor" strokeWidth="1.3"/><circle cx="8" cy="8" r="2" fill="currentColor"/></svg>
            </div>
            <span>Grant screen recording permission so Tada can observe your workflow</span>
          </div>
          <div className="welcome-feature">
            <div className="wf-icon">
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M8 2v4l3 2" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/><path d="M2.5 8.5A5.5 5.5 0 1013.5 8" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/></svg>
            </div>
            <span>Choose your prediction model</span>
          </div>
          <div className="welcome-feature">
            <div className="wf-icon">
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M4 12V7M8 12V4M12 12V9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
            </div>
            <span>Connect your API keys</span>
          </div>
        </div>
      </div>
      <div className="btn-row">
        <div></div>
        <button className="btn btn-primary" onClick={onStart}>Get Started</button>
      </div>
    </div>
  );
}
