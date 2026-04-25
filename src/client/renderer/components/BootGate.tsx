import React from "react";
import { useAppContext } from "../context/AppContext";
import { useWaitForServices, type ServicesStatus } from "../hooks/useWaitForServices";

const CHECKLIST: { key: keyof ServicesStatus; label: string }[] = [
  { key: "services_started", label: "Starting services" },
  { key: "screen_frame_fresh", label: "Capturing your screen" },
  { key: "tabracadabra_ready", label: "Tabracadabra ready" },
];

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
  const { status, ready, error, retry } = useWaitForServices({
    enabled: app.connected,
    // Cold-boot init_model + connector startup can legitimately take 1–2
    // minutes on a slow machine; only surface the "try again" error if we're
    // well past that.
    timeoutMs: 180_000,
  });

  if (ready) return <>{children}</>;

  return (
    <>
      <div className="drag-topbar" />
      <div className="boot-gate">
        <div className="boot-gate-card">
          <div className="boot-gate-title">Getting ready…</div>
          <p className="boot-gate-desc">
            Spinning up Tada. This can take a minute or two.
          </p>
          <ul className="boot-gate-checklist">
            {CHECKLIST.map((item) => {
              const done = status[item.key];
              return (
                <li
                  key={item.key}
                  className={done ? "boot-gate-item done" : "boot-gate-item"}
                >
                  <span className="boot-gate-marker" aria-hidden="true">
                    {done ? (
                      <svg
                        width="14"
                        height="14"
                        viewBox="0 0 16 16"
                        fill="none"
                      >
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
                        className="spinner"
                        style={{ width: 12, height: 12, borderWidth: 2 }}
                      />
                    )}
                  </span>
                  <span>{item.label}</span>
                </li>
              );
            })}
          </ul>
          {error && (
            <div className="boot-gate-error">
              <p>{error}</p>
              <button className="btn btn-primary" onClick={retry}>
                Try again
              </button>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
