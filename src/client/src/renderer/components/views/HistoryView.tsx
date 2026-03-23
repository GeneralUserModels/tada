import { useAppContext, HistoryItem } from "../../context/AppContext";

const BADGE_CLASS: Record<HistoryItem["type"], string> = {
  prediction: "badge-prediction",
  label: "badge-label",
  training: "badge-training",
};

export function HistoryView() {
  const { state } = useAppContext();

  return (
    <div id="history-view" className="view active">
      <section className="glass-card full-height">
        <div className="card-header">
          <h2>Activity Log</h2>
        </div>
        <div className="history-feed">
          {state.historyItems.length === 0 ? (
            <span className="empty-state" style={{ padding: "12px 0", display: "block" }}>
              No activity yet...
            </span>
          ) : (
            state.historyItems.map((item) => (
              <div key={item.id} className="history-item">
                <span className={`history-badge ${BADGE_CLASS[item.type]}`}>{item.type}</span>
                <div>
                  <div className="history-text">{item.text.substring(0, 140)}</div>
                  {item.timestamp && (
                    <div className="history-meta">{item.timestamp}</div>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      </section>
    </div>
  );
}
