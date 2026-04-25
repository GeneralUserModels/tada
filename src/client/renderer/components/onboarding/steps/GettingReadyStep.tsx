import React, { useEffect, useRef } from "react";
import { useWaitForServices, type ServicesStatus } from "../../../hooks/useWaitForServices";

type Props = {
  onContinue: () => void;
};

const CHECKLIST: { key: keyof ServicesStatus; label: string }[] = [
  { key: "services_started", label: "Starting services" },
  { key: "screen_frame_fresh", label: "Capturing your screen" },
  { key: "tabracadabra_ready", label: "Tabracadabra ready" },
];

export function GettingReadyStep({ onContinue }: Props) {
  // Onboarding is the only place that calls finalize — it flips
  // onboarding_complete=true and kicks start_services. The dashboard's
  // BootGate uses the same hook with finalize=false (lifespan already did it).
  const { status, ready, error, retry } = useWaitForServices({
    enabled: true,
    finalize: true,
    timeoutMs: 30_000,
  });

  const advancedRef = useRef(false);
  const onContinueRef = useRef(onContinue);
  onContinueRef.current = onContinue;

  useEffect(() => {
    if (!ready || advancedRef.current) return;
    advancedRef.current = true;
    // Tiny delay so the user actually sees the final check land before the
    // wizard slides on.
    const t = window.setTimeout(() => onContinueRef.current(), 350);
    return () => window.clearTimeout(t);
  }, [ready]);

  return (
    <div className="page active" style={{ maxWidth: 420 }}>
      <div className="page-icon">
        <svg width="22" height="22" viewBox="0 0 16 16" fill="none">
          <path
            d="M8 2v4l3 2"
            stroke="currentColor"
            strokeWidth="1.3"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <path
            d="M2.5 8.5A5.5 5.5 0 1013.5 8"
            stroke="currentColor"
            strokeWidth="1.3"
            strokeLinecap="round"
          />
        </svg>
      </div>
      <div className="page-title">Getting ready…</div>
      <p className="page-desc">
        Spinning up the parts of Tada you just configured. This usually takes a
        few seconds.
      </p>

      <div className="glass-card">
        <div className="welcome-features">
          {CHECKLIST.map((item) => {
            const done = status[item.key];
            return (
              <div className="welcome-feature" key={item.key}>
                <div className="wf-icon" aria-hidden="true">
                  {done ? (
                    <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                      <path
                        d="M4 8l3 3 5-6"
                        stroke="currentColor"
                        strokeWidth="1.6"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  ) : (
                    <span
                      className="startup-spinner"
                      style={{ width: 12, height: 12, borderWidth: 2 }}
                    />
                  )}
                </div>
                <span style={{ opacity: done ? 1 : 0.7 }}>{item.label}</span>
              </div>
            );
          })}
        </div>
      </div>

      {error && (
        <p
          className="page-desc"
          style={{ marginTop: 16, color: "var(--text-secondary)" }}
        >
          {error}
        </p>
      )}

      <div className="btn-row">
        <div />
        {error ? (
          <button className="btn btn-primary" onClick={retry}>
            Try again
          </button>
        ) : (
          <div className="startup-indicator">
            <span className="startup-spinner" />
            <span>Working…</span>
          </div>
        )}
      </div>
    </div>
  );
}
