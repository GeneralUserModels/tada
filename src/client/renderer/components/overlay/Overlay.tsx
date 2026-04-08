import React, { useEffect, useRef, useState } from "react";

type OverlayStatus = "waiting" | "flushing" | "predicted";

interface OverlayState {
  status: OverlayStatus;
  actions: string[];
}

function parseActions(text: string): string[] {
  const matches = text.match(/<action>([\s\S]*?)<\/action>/g);
  if (matches) {
    return matches.map((m) => m.replace(/<\/?action>/g, "").trim());
  }
  const clean = text.replace(/<[^>]+>/g, "").trim();
  return clean ? [clean] : [];
}

export function Overlay() {
  const [state, setState] = useState<OverlayState>({ status: "waiting", actions: [] });
  const overlayRef = useRef<HTMLDivElement>(null);
  const registered = useRef(false);

  // Resize Electron window to fit content after every render
  useEffect(() => {
    if (!overlayRef.current) return;
    const height = Math.max(80, Math.min(500, overlayRef.current.scrollHeight + 8));
    window.tada.resizeOverlay(height);
  });

  useEffect(() => {
    if (registered.current) return;
    registered.current = true;

    window.tada.onOverlayWaiting(() => {
      setState({ status: "waiting", actions: [] });
    });

    window.tada.onOverlayFlushing(() => {
      setState({ status: "flushing", actions: [] });
    });

    window.tada.onOverlayPrediction((data) => {
      if (data.error || !data.actions) {
        setState({ status: "waiting", actions: [] });
        return;
      }
      const parsed = parseActions(data.actions);
      if (parsed.length > 0) {
        setState({ status: "predicted", actions: parsed });
      } else {
        setState({ status: "waiting", actions: [] });
      }
    });
  }, []);

  const titleMap: Record<OverlayStatus, string> = {
    waiting: "Not Ready",
    flushing: "Syncing\u2026",
    predicted: "Predicted Actions",
  };

  const iconMap: Record<OverlayStatus, string> = {
    waiting: "\u25CB",
    flushing: "\u21BB",
    predicted: "\u2713",
  };

  const { status, actions } = state;

  return (
    <div id="overlay" ref={overlayRef}>
      <div id="overlay-header">
        <span id="overlay-icon" className={`header-icon${status === "predicted" ? " predicted" : status === "flushing" ? " flushing" : ""}`}>
          {iconMap[status]}
        </span>
        <span id="overlay-title" className={status === "predicted" ? "predicted" : status === "flushing" ? "flushing" : ""}>
          {titleMap[status]}
        </span>
      </div>
      <div id="overlay-divider"></div>
      <div id="overlay-content" className={status === "predicted" ? "actions" : ""}>
        {status === "predicted" ? (
          actions.map((action, i) => (
            <div key={i} className="action-item">
              <span className="action-num">{i + 1}.</span>
              <span className="action-text">{action}</span>
            </div>
          ))
        ) : status === "flushing" ? (
          "Labeling recent activity for fresh predictions\u2026"
        ) : (
          <>Still labeling data\u2026<br />Try again in a moment.</>
        )}
      </div>
    </div>
  );
}
