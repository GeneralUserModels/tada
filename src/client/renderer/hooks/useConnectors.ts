import { useState, useCallback, useEffect } from "react";

export function useConnectors() {
  const [connectors, setConnectors] = useState<Record<string, ConnectorInfo>>({});
  const [loading, setLoading] = useState(false);
  const [toggling, setToggling] = useState<Set<string>>(new Set());

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const status = await window.powernap.getConnectorStatus();
      setConnectors(status);
    } catch {
      // silently ignore — caller handles empty state
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    window.powernap.onConnectorUpdate((data) => {
      setConnectors(prev => ({
        ...prev,
        [data.name]: { ...prev[data.name], error: data.error, enabled: data.enabled },
      }));
    });
  }, []);

  const toggle = async (name: string, enabled: boolean) => {
    setToggling(prev => new Set(prev).add(name));
    try {
      await window.powernap.updateConnector(name, enabled);
      await load();
    } finally {
      setToggling(prev => { const next = new Set(prev); next.delete(name); return next; });
    }
  };

  const connectGoogle = async (svc: string, otherIsOn: boolean) => {
    const scope = otherIsOn ? "calendar,gmail" : svc;
    const ok = await window.powernap.connectorConnectGoogle(scope);
    if (ok) {
      await window.powernap.updateConnector(svc, true);
    }
    await load();
    return ok;
  };

  const connectOutlook = async () => {
    const ok = await window.powernap.connectorConnectOutlook();
    if (ok) {
      await window.powernap.updateConnector("outlook_calendar", true);
      await window.powernap.updateConnector("outlook_email", true);
    }
    await load();
    return ok;
  };

  const retry = async (name: string) => {
    await window.powernap.updateConnector(name, true);
    await load();
  };

  return { connectors, loading, load, toggle, toggling, connectGoogle, connectOutlook, retry };
}
