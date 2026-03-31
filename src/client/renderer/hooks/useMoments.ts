import { useState, useCallback, useEffect } from "react";
import { getMomentsResults } from "../api/client";
import { on as sseOn } from "../api/sse";

export function useMoments() {
  const [results, setResults] = useState<MomentResult[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getMomentsResults();
      setResults(res);
    } catch (e) {
      console.error("[moments] load failed:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    sseOn("moment_completed", () => load());
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return { results, loading, load };
}
