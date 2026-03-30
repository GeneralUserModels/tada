import { useState, useCallback, useEffect } from "react";
import { getConnectors, updateConnector, startGoogleAuth, startOutlookAuth, disconnectGoogle, disconnectOutlook } from "../api/client";
import { on as sseOn } from "../api/sse";

export function useConnectors() {
  const [connectors, setConnectors] = useState<Record<string, ConnectorInfo>>({});
  const [loading, setLoading] = useState(false);
  const [toggling, setToggling] = useState<Set<string>>(new Set());

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const status = await getConnectors() as Record<string, ConnectorInfo>;
      setConnectors(status);
    } catch (e) {
      console.error("[connectors] load failed:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    sseOn("connectors", () => load());
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const toggle = async (name: string, enabled: boolean) => {
    setToggling(prev => new Set(prev).add(name));
    try {
      await updateConnector(name, enabled);
      await load();
    } finally {
      setToggling(prev => { const next = new Set(prev); next.delete(name); return next; });
    }
  };

  const connectGoogle = async (_svc: string, _otherIsOn: boolean) => {
    // Python OAuth always requests all Google scopes at once
    await startGoogleAuth();
    await load();
  };

  const connectOutlook = async () => {
    await startOutlookAuth();
    await load();
  };

  const disconnectGoogleAll = async () => {
    await disconnectGoogle();
    await load();
  };

  const disconnectOutlookAll = async () => {
    await disconnectOutlook();
    await load();
  };

  const retry = async (name: string) => {
    await updateConnector(name, true);
    await load();
  };

  return { connectors, loading, load, toggle, toggling, connectGoogle, connectOutlook, disconnectGoogleAll, disconnectOutlookAll, retry };
}
