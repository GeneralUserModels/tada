import { useEffect, useState } from "react";
import { finalizeOnboarding, getServicesStatus } from "../api/client";

export type ServicesStatus = {
  services_started: boolean;
  tabracadabra_ready: boolean;
  screen_frame_fresh: boolean;
  screen_paused: boolean;
};

const EMPTY: ServicesStatus = {
  services_started: false,
  tabracadabra_ready: false,
  screen_frame_fresh: false,
  // Default to paused until the server reports otherwise — avoids gating boot
  // on a screen frame check before we've heard from the connector.
  screen_paused: true,
};

const POLL_INTERVAL_MS = 500;

export type UseWaitForServicesOpts = {
  // Don't start polling until the renderer has actually wired up to the
  // server (e.g. dashboard waits for SERVER_READY, onboarding waits for the
  // step to mount).
  enabled: boolean;
  // Onboarding's "Getting ready" step uses this to also POST /finalize once
  // before polling. The dashboard's BootGate leaves it false — for returning
  // users the lifespan handler has already kicked start_services.
  finalize?: boolean;
  // When false, don't gate readiness on `tabracadabra_ready`. The backend
  // never starts the event tap when the user has tabracadabra disabled (or
  // the feature flag is off), so waiting for it would hang forever.
  requireTabracadabra?: boolean;
  // When false, don't gate readiness on `screen_frame_fresh` regardless of
  // backend pause state. Onboarding sets this from the granted permission.
  // For the dashboard's BootGate this stays true and the hook defers to the
  // runtime `screen_paused` flag in the status response: if the connector
  // was paused on app close, no frame ever lands and we'd hang forever.
  requireScreen?: boolean;
};

/**
 * Polls /api/services/status and reports when all background services
 * (connectors, screen capture, Tabracadabra event tap) are live.
 *
 * Used by both the onboarding "Getting ready" step and the dashboard
 * BootGate so there's a single definition of "system is calm enough to use".
 *
 * There is intentionally no timeout / error path: cold boot of init_model +
 * connectors can legitimately take a couple of minutes, and the only useful
 * thing we can tell the user is "keep waiting". Surfacing a "try again"
 * button just punishes the user for a slow machine.
 */
export function useWaitForServices({
  enabled,
  finalize = false,
  requireTabracadabra = true,
  requireScreen = true,
}: UseWaitForServicesOpts) {
  const [status, setStatus] = useState<ServicesStatus>(EMPTY);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!enabled || ready) return;
    let cancelled = false;
    let timer: number | null = null;
    setStatus(EMPTY);

    const sleep = (ms: number) =>
      new Promise<void>((resolve) => {
        timer = window.setTimeout(resolve, ms);
      });

    const poll = async () => {
      while (!cancelled) {
        try {
          const next = await getServicesStatus();
          if (cancelled) return;
          setStatus(next);
          // Skip the screen-frame check when the caller didn't ask for it OR
          // when the backend reports the connector paused — a paused connector
          // never publishes a frame, so requiring `screen_frame_fresh` would
          // hang the boot gate indefinitely.
          const screenOk = (
            !requireScreen || next.screen_paused || next.screen_frame_fresh
          );
          if (
            next.services_started &&
            (!requireTabracadabra || next.tabracadabra_ready) &&
            screenOk
          ) {
            setReady(true);
            return;
          }
        } catch {
          // Server is probably still warming up — keep polling.
        }
        await sleep(POLL_INTERVAL_MS);
      }
    };

    (async () => {
      if (finalize) {
        // Retry finalize until the server accepts it. Same philosophy as the
        // poll loop: a transient failure shouldn't wedge the user on an
        // error screen.
        while (!cancelled) {
          try {
            await finalizeOnboarding();
            break;
          } catch (e) {
            if (cancelled) return;
            console.error("[boot] finalize failed, retrying", e);
            await sleep(POLL_INTERVAL_MS);
          }
        }
      }
      if (!cancelled) poll();
    })();

    return () => {
      cancelled = true;
      if (timer !== null) window.clearTimeout(timer);
    };
  }, [enabled, finalize, ready, requireTabracadabra, requireScreen]);

  return { status, ready };
}
