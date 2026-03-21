import { useEffect, useRef, useState } from "react";
import { useAppContext } from "../../context/AppContext";
import { useConnectors } from "../../hooks/useConnectors";
import { ConnectorItem, CONNECTOR_META } from "../connectors/ConnectorItem";

export function ConnectorsView() {
  const { state, dispatch } = useAppContext();
  const { connectors, loading, load, toggle, connectGoogle, connectOutlook, retry } = useConnectors();
  const [connectingName, setConnectingName] = useState<string | null>(null);
  const prevPermModal = useRef(state.permModal);

  useEffect(() => {
    load();
  }, [load]);

  // Reload connectors when permission modal closes (permission may have been granted)
  useEffect(() => {
    if (prevPermModal.current !== null && state.permModal === null) {
      load();
    }
    prevPermModal.current = state.permModal;
  }, [state.permModal, load]);

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

  const handleCheckPermission = async (name: string) => {
    return window.powernap.checkConnectorPermission(name);
  };

  const handleOpenPermModal = (name: string) => {
    dispatch({ type: "OPEN_PERM_MODAL", connectorName: name });
  };

  return (
    <div id="connectors-view" className="view active">
      <section className="glass-card">
        {loading ? (
          <div style={{ color: "#9BA896", fontSize: 12, padding: 12 }}>Loading...</div>
        ) : Object.keys(connectors).length === 0 ? (
          <div style={{ color: "#9BA896", fontSize: 12, padding: 12 }}>
            Unable to load connector status.
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            {Object.entries(connectors)
              .filter(([name]) => CONNECTOR_META[name])
              .map(([name, info]) => (
                <ConnectorItem
                  key={name}
                  name={name}
                  info={info}
                  calendarOn={calendarOn}
                  gmailOn={gmailOn}
                  onToggle={toggle}
                  onConnectGoogle={handleConnectGoogle}
                  onConnectOutlook={handleConnectOutlook}
                  onFix={handleOpenPermModal}
                  onRetry={retry}
                  onCheckPermission={handleCheckPermission}
                  onOpenPermModal={handleOpenPermModal}
                />
              ))}
          </div>
        )}
      </section>
    </div>
  );
}
