import { useState, useCallback, useEffect } from "react";
import { updateConnector } from "../api/client";

export function useConnectors() {
  const [connectors, setConnectors] = useState<Record<string, ConnectorInfo>>({});
  const [loading, setLoading] = useState(true);
  const [toggling, setToggling] = useState<Set<string>>(new Set());

  const load = useCallback(async () => {
    setLoading(true);
    try {
      // getConnectorStatus stays in IPC — it combines Python state with main-process
      // auth state (token file existence, config) that the renderer can't access directly.
      const status = await window.powernap.getConnectorStatus();
      setConnectors(status);
    } catch {
      // silently ignore — caller handles empty state
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    window.powernap.onConnectorUpdate(() => {
      load();
    });
  }, [load]);

  const toggle = async (name: string, enabled: boolean) => {
    setToggling(prev => new Set(prev).add(name));
    try {
      await updateConnector(name, enabled);
      await load();
    } finally {
      setToggling(prev => { const next = new Set(prev); next.delete(name); return next; });
    }
  };

  const connectGoogle = async (svc: string, otherIsOn: boolean) => {
    const scope = otherIsOn ? "calendar,gmail" : svc;
    const ok = await window.powernap.connectorConnectGoogle(scope);
    if (ok) {
      await updateConnector(svc, true);
    }
    await load();
    return ok;
  };

  const connectOutlook = async () => {
    const ok = await window.powernap.connectorConnectOutlook();
    if (ok) {
      await updateConnector("outlook_calendar", true);
      await updateConnector("outlook_email", true);
    }
    await load();
    return ok;
  };

  const retry = async (name: string) => {
    await updateConnector(name, true);
    await load();
  };

  return { connectors, loading, load, toggle, toggling, connectGoogle, connectOutlook, retry };
}
