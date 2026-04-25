import React, { useEffect, useRef, useState } from "react";
import { finalizeOnboarding, getServicesStatus } from "../../../api/client";

type Props = {
  onContinue: () => void;
};

type Status = {
  services_started: boolean;
  tabracadabra_ready: boolean;
  screen_frame_fresh: boolean;
};

const POLL_INTERVAL_MS = 500;
// If something is wedged (no screen frame, tabracadabra failed to install its
// event tap, etc.), surface a recoverable error rather than spinning forever.
const TIMEOUT_MS = 30_000;

const CHECKLIST: { key: keyof Status; label: string }[] = [
  { key: "services_started", label: "Starting services" },
  { key: "screen_frame_fresh", label: "Capturing your screen" },
  { key: "tabracadabra_ready", label: "Tabracadabra ready" },
];

const EMPTY_STATUS: Status = {
  services_started: false,
  tabracadabra_ready: false,
  screen_frame_fresh: false,
};

export function GettingReadyStep({ onContinue }: Props) {
  const [status, setStatus] = useState<Status>(EMPTY_STATUS);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  // Refs so the polling effect can read the latest values without re-subscribing.
  const advancedRef = useRef(false);
  const onContinueRef = useRef(onContinue);
  onContinueRef.current = onContinue;

  useEffect(() => {
    let cancelled = false;
    setError(null);
    setStatus(EMPTY_STATUS);

    const startedAt = Date.now();
    let pollTimer: number | null = null;

    const poll = async () => {
      try {
        const next = await getServicesStatus();
        if (cancelled) return;
        setStatus(next);
        if (
          next.services_started &&
          next.tabracadabra_ready &&
          next.screen_frame_fresh
        ) {
          if (!advancedRef.current) {
            advancedRef.current = true;
            // Tiny delay so the user actually sees the final check land before
            // the wizard slides on.
            window.setTimeout(() => {
              if (!cancelled) onContinueRef.current();
            }, 350);
          }
          return;
        }
      } catch {
        // Server might still be coming up — keep polling, only the timeout
        // surfaces an error.
      }
      if (Date.now() - startedAt > TIMEOUT_MS && !advancedRef.current) {
        setError(
          "Things are taking longer than expected. Make sure screen recording is granted, then try again.",
        );
        return;
      }
      pollTimer = window.setTimeout(poll, POLL_INTERVAL_MS);
    };

    (async () => {
      // Idempotent on the server: sets onboarding_complete=true (no-op if
      // already true) and kicks start_services (early-returns if already
      // running). The connector list was persisted earlier via PUT /api/settings.
      try {
        await finalizeOnboarding();
      } catch (e) {
        if (cancelled) return;
        console.error("[onboarding] finalize failed", e);
        setError("Couldn't start services. Please try again.");
        return;
      }
      if (!cancelled) poll();
    })();

    return () => {
      cancelled = true;
      if (pollTimer !== null) window.clearTimeout(pollTimer);
    };
    // attempt is included so the "Try again" button can re-run the whole effect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attempt]);

  const handleRetry = () => {
    advancedRef.current = false;
    setAttempt((n) => n + 1);
  };

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
          <button className="btn btn-primary" onClick={handleRetry}>
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
