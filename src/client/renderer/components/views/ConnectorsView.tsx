import React, { useEffect, useState, useRef } from "react";
import { useAppContext, HistoryItem } from "../../context/AppContext";
import { useFeatureFlags, getFlag } from "../../featureFlags";
import * as api from "../../api/client";
import { useConnectors } from "../../hooks/useConnectors";
import { ConnectorItem, CONNECTOR_META } from "../connectors/ConnectorItem";

const BADGE_CLASS: Record<HistoryItem["type"], string> = {
  prediction: "badge-prediction",
  label: "badge-label",
  training: "badge-training",
};

export function ConnectorsView() {
  const { state, dispatch } = useAppContext();
  const featureFlags = useFeatureFlags();
  const { connectors, loading, load, toggle, toggling, connectGoogle, connectOutlook, retry } = useConnectors();
  const [connectingName, setConnectingName] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Poll for services_started when connected but services not ready
  useEffect(() => {
    if (state.connected && !state.servicesReady) {
      pollRef.current = setInterval(async () => {
        const status = await api.getStatus() as Record<string, unknown>;
        if (status.services_started) {
          dispatch({ type: "STATUS_UPDATE", data: status as never });
        }
      }, 2000);
      return () => { if (pollRef.current) clearInterval(pollRef.current); };
    }
  }, [state.connected, state.servicesReady, dispatch]);

  // Load connectors when services become ready
  useEffect(() => {
    if (state.servicesReady) {
      load();
    }
  }, [state.servicesReady, load]);

  const calendarOn = !!(connectors.calendar?.enabled && connectors.calendar?.available);
  const gmailOn = !!(connectors.gmail?.enabled && connectors.gmail?.available);

  const handleConnectGoogle = async (svc: string, otherIsOn: boolean) => {
    setConnectingName(svc);
    await connectGoogle(svc, otherIsOn);
    setConnectingName(null);
  };

  const handleConnectOutlook = async () => {
    setConnectingName("outlook_calendar");
    await connectOutlook();
    setConnectingName(null);
  };

  return (
    <div id="connectors-view" className="view active">
      <section className="glass-card">
        <div className="card-header">
          <h2>Connectors</h2>
        </div>
        {!state.servicesReady ? (
          <div style={{ color: "#9BA896", fontSize: 13, padding: "24px 12px", display: "flex", alignItems: "center", gap: 10 }}>
            <span className="spinner" />
            Starting up (this can take a few minutes)...
          </div>
        ) : loading ? (
          <div style={{ color: "#9BA896", fontSize: 12, padding: 12 }}>Loading...</div>
        ) : Object.keys(connectors).length === 0 ? (
          <div style={{ color: "#9BA896", fontSize: 12, padding: 12 }}>
            Unable to load connector status.
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            {Object.entries(connectors)
              .filter(([name]) => CONNECTOR_META[name] && getFlag(featureFlags, `connector_${name}`))
              .sort(([a], [b]) => {
                const keys = Object.keys(CONNECTOR_META);
                return keys.indexOf(a) - keys.indexOf(b);
              })
              .map(([name, info]) => (
                <ConnectorItem
                  key={name}
                  name={name}
                  info={info}
                  calendarOn={calendarOn}
                  gmailOn={gmailOn}
                  toggling={toggling.has(name) || connectingName === name}
                  onToggle={toggle}
                  onConnectGoogle={handleConnectGoogle}
                  onConnectOutlook={handleConnectOutlook}
                  onRetry={retry}
                />
              ))}
          </div>
        )}
      </section>

      <section className="glass-card">
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
