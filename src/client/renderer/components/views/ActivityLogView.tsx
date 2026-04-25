import React from "react";
import { useAppContext, HistoryItem } from "../../context/AppContext";

const BADGE_CLASS: Record<HistoryItem["type"], string> = {
  prediction: "badge-prediction",
  label: "badge-label",
  training: "badge-training",
};

export function ActivityLogView() {
  const { state } = useAppContext();

  return (
    <div id="activity-view" className="view active">
      <section className="glass-card">
        <div className="card-header">
          <h2>Activity</h2>
        </div>
        <div className="history-feed">
          {state.historyItems.length === 0 ? (
            <span className="empty-state" style={{ padding: "12px 0", display: "block" }}>
              No activity yet...
            </span>
          ) : (
            state.historyItems.map((item, idx) => {
              // historyItems is newest-first; show the caption only when it
              // differs from the next-older entry (i.e. on first entry into
              // a new screen state) so we don't repeat the same description.
              const olderCaption = state.historyItems[idx + 1]?.denseCaption ?? "";
              const showCaption = !!item.denseCaption && item.denseCaption !== olderCaption;
              return (
                <div key={item.id} className="history-item">
                  <span className={`history-badge ${BADGE_CLASS[item.type]}`}>{item.type}</span>
                  <div className="history-content">
                    <div className="history-text">{item.text.substring(0, 140)}</div>
                    {showCaption && (
                      <div className="history-caption">{item.denseCaption}</div>
                    )}
                    {item.timestamp && (
                      <div className="history-meta">{item.timestamp}</div>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>
      </section>
    </div>
  );
}
