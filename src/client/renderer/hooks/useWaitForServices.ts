import { useEffect, useState } from "react";
import { finalizeOnboarding, getServicesStatus } from "../api/client";

export type ServicesStatus = {
  services_started: boolean;
  tabracadabra_ready: boolean;
  screen_frame_fresh: boolean;
};

const EMPTY: ServicesStatus = {
  services_started: false,
  tabracadabra_ready: false,
  screen_frame_fresh: false,
};

const POLL_INTERVAL_MS = 500;
const DEFAULT_TIMEOUT_MS = 60_000;

export type UseWaitForServicesOpts = {
  // Don't start polling until the renderer has actually wired up to the
  // server (e.g. dashboard waits for SERVER_READY, onboarding waits for the
  // step to mount).
  enabled: boolean;
  // Onboarding's "Getting ready" step uses this to also POST /finalize once
  // before polling. The dashboard's BootGate leaves it false — for returning
  // users the lifespan handler has already kicked start_services.
  finalize?: boolean;
  timeoutMs?: number;
};

/**
 * Polls /api/services/status and reports when all background services
 * (connectors, screen capture, Tabracadabra event tap) are live.
 *
 * Used by both the onboarding "Getting ready" step and the dashboard
 * BootGate so there's a single definition of "system is calm enough to use".
 */
export function useWaitForServices({
  enabled,
  finalize = false,
  timeoutMs = DEFAULT_TIMEOUT_MS,
}: UseWaitForServicesOpts) {
  const [status, setStatus] = useState<ServicesStatus>(EMPTY);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!enabled || ready) return;
    let cancelled = false;
    let timer: number | null = null;
    setError(null);
    setStatus(EMPTY);

    const startedAt = Date.now();
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
          setReady(true);
          return;
        }
      } catch {
        // Server is probably still warming up — keep polling, only the
        // wall-clock timeout surfaces an error.
      }
      if (Date.now() - startedAt > timeoutMs) {
        setError(
          "Things are taking longer than expected. Make sure screen recording is granted, then try again.",
        );
        return;
      }
      timer = window.setTimeout(poll, POLL_INTERVAL_MS);
    };

    (async () => {
      if (finalize) {
        try {
          await finalizeOnboarding();
        } catch (e) {
          if (cancelled) return;
          console.error("[boot] finalize failed", e);
          setError("Couldn't start services. Please try again.");
          return;
        }
      }
      if (!cancelled) poll();
    })();

    return () => {
      cancelled = true;
      if (timer !== null) window.clearTimeout(timer);
    };
  }, [enabled, attempt, finalize, timeoutMs, ready]);

  const retry = () => {
    setReady(false);
    setAttempt((n) => n + 1);
  };

  return { status, ready, error, retry };
}
