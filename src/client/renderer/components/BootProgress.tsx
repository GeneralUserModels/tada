import React, { useEffect, useState } from "react";
import type { ServicesStatus } from "../hooks/useWaitForServices";

/**
 * Single source of truth for the "system services warming up" view used by
 * both the dashboard's BootGate and onboarding's GettingReadyStep.
 *
 * The progress bar is intentionally a fixed-time visual: cold boot of
 * init_model + connectors empirically takes ~30s on a fast machine and up to
 * a minute on a slow one, but the renderer can't actually predict it.
 * Showing a bar that creeps to 95% over ~1 min and then jumps to 100% the
 * moment services report ready is way nicer than a bare spinner where the
 * user can't tell if anything is happening.
 */

const ESTIMATED_TOTAL_MS = 60_000; // ~1 min — fits the typical cold boot
const SOFT_CAP = 0.95; // hold here until the server actually says ready
const TICK_MS = 200;

export const BOOT_CHECKLIST: { key: keyof ServicesStatus; label: string }[] = [
  { key: "services_started", label: "Starting services" },
  { key: "screen_frame_fresh", label: "Capturing your screen" },
  { key: "tabracadabra_ready", label: "Tabracadabra ready" },
];

type Props = {
  status: ServicesStatus;
  ready: boolean;
  requireTabracadabra?: boolean;
  requireScreen?: boolean;
};

export function BootProgress({ status, ready, requireTabracadabra = true, requireScreen = true }: Props) {
  const [pct, setPct] = useState(0);

  useEffect(() => {
    if (ready) {
      setPct(1);
      return;
    }
    const startedAt = Date.now();
    const id = window.setInterval(() => {
      const elapsed = Date.now() - startedAt;
      const ratio = Math.min((elapsed / ESTIMATED_TOTAL_MS) * SOFT_CAP, SOFT_CAP);
      setPct((prev) => (ratio > prev ? ratio : prev));
    }, TICK_MS);
    return () => window.clearInterval(id);
  }, [ready]);

  return (
    <div className="boot-progress">
      <div className="boot-progress-bar" aria-hidden="true">
        <div
          className="boot-progress-fill"
          style={{ width: `${Math.round(pct * 100)}%` }}
        />
      </div>
      <ul className="boot-progress-checklist">
        {BOOT_CHECKLIST.filter((item) => {
          if (!requireTabracadabra && item.key === "tabracadabra_ready") return false;
          if (!requireScreen && item.key === "screen_frame_fresh") return false;
          return true;
        }).map((item) => {
          const done = status[item.key];
          return (
            <li
              key={item.key}
              className={done ? "boot-progress-item done" : "boot-progress-item"}
            >
              <span className="boot-progress-marker" aria-hidden="true">
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
                  <span className="boot-progress-spinner" aria-hidden="true" />
                )}
              </span>
              <span>{item.label}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
