import React from "react";
import { useAppContext } from "../context/AppContext";
import { useWaitForServices } from "../hooks/useWaitForServices";
import { BootProgress } from "./BootProgress";

/**
 * Wraps the dashboard so the user only sees real UI once the heavy services
 * (connectors, screen recorder, Tabracadabra event tap, predictor) are up.
 *
 * Without this, returning users land on the dashboard ~immediately while the
 * Python lifespan is still running init_model. Pressing Option+Tab in that
 * window either does nothing (event tap not installed yet) or limps along
 * because Quartz event posts share the GIL with init_model. Holding the
 * dashboard back for a few seconds removes the entire footgun.
 */
export function BootGate({ children }: { children: React.ReactNode }) {
  const { state: app } = useAppContext();
  // Only start polling once the renderer is wired up to the server. Before
  // SERVER_READY fires the api client has no URL and getServicesStatus would
  // just throw on every poll.
  const { status, ready } = useWaitForServices({
    enabled: app.connected,
  });

  if (ready) return <>{children}</>;

  return (
    <>
      <div className="drag-topbar" />
      <div className="boot-gate">
        <div className="boot-gate-card">
          <div className="boot-gate-title">Getting ready…</div>
          <p className="boot-gate-desc">
            Spinning up Tada. This usually takes about a minute.
          </p>
          <BootProgress status={status} ready={ready} />
        </div>
      </div>
    </>
  );
}
