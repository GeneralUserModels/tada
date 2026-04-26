import React, { useEffect, useRef } from "react";
import { useWaitForServices } from "../../../hooks/useWaitForServices";
import { BootProgress } from "../../BootProgress";

type Props = {
  onContinue: () => void;
  // True when the user has tabracadabra on — gates whether we wait for the
  // event tap to come up. Passed through from Onboarding so the wait matches
  // what the backend actually starts.
  requireTabracadabra?: boolean;
  // True when the user granted screen recording permission and the screen
  // connector will be in `enabled_connectors`. When false, no frame ever
  // lands so we'd hang on `screen_frame_fresh`.
  requireScreen?: boolean;
};

export function GettingReadyStep({ onContinue, requireTabracadabra = true, requireScreen = true }: Props) {
  // Onboarding is the only place that calls finalize — it flips
  // onboarding_complete=true and kicks start_services. The dashboard's
  // BootGate uses the same hook with finalize=false (lifespan already did it).
  const { status, ready } = useWaitForServices({
    enabled: true,
    finalize: true,
    requireTabracadabra,
    requireScreen,
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
        Go ahead and use your computer normally for a minute or two while Tada
        finishes setting up. <b>Click around! Look at things! Then come back here...</b>
      </p>

      <div className="glass-card">
        <BootProgress
          status={status}
          ready={ready}
          requireTabracadabra={requireTabracadabra}
          requireScreen={requireScreen}
        />
      </div>
    </div>
  );
}
