import { useState, useCallback, useEffect, useRef } from "react";
import {
  getMomentsResults,
  updateMomentState,
  updateMomentSchedule,
  recordMomentView,
  recordMomentViewEnd,
} from "../api/client";
import { on as sseOn } from "../api/sse";

export function useMoments() {
  const [results, setResults] = useState<MomentResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [showDismissed, setShowDismissed] = useState(false);
  const viewStartRef = useRef<{ slug: string; ts: number } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    const res = await getMomentsResults(showDismissed);
    setResults(res);
    setLoading(false);
  }, [showDismissed]);

  useEffect(() => {
    sseOn("moment_completed", () => load());
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const dismiss = useCallback(async (slug: string) => {
    setResults((prev) => prev.filter((r) => r.slug !== slug));
    await updateMomentState(slug, { dismissed: true });
  }, []);

  const pin = useCallback(async (slug: string) => {
    setResults((prev) =>
      prev.map((r) => (r.slug === slug ? { ...r, pinned: true, dismissed: false } : r))
    );
    await updateMomentState(slug, { pinned: true });
  }, []);

  const unpin = useCallback(async (slug: string) => {
    setResults((prev) =>
      prev.map((r) => (r.slug === slug ? { ...r, pinned: false } : r))
    );
    await updateMomentState(slug, { pinned: false });
  }, []);

  const editSchedule = useCallback(async (slug: string, frequency: string, schedule: string) => {
    await updateMomentSchedule(slug, { frequency, schedule });
    setResults((prev) =>
      prev.map((r) =>
        r.slug === slug ? { ...r, frequency_override: frequency, schedule_override: schedule } : r
      )
    );
  }, []);

  const startView = useCallback((slug: string) => {
    viewStartRef.current = { slug, ts: Date.now() };
    recordMomentView(slug);
  }, []);

  const endView = useCallback((slug: string) => {
    const ref = viewStartRef.current;
    if (ref && ref.slug === slug) {
      const duration_ms = Date.now() - ref.ts;
      if (duration_ms > 500) {
        recordMomentViewEnd(slug, { duration_ms });
      }
      viewStartRef.current = null;
    }
  }, []);

  const toggleShowDismissed = useCallback(() => {
    setShowDismissed((prev) => !prev);
  }, []);

  // Reload when showDismissed changes
  useEffect(() => {
    load();
  }, [showDismissed]); // eslint-disable-line react-hooks/exhaustive-deps

  return {
    results,
    loading,
    load,
    showDismissed,
    toggleShowDismissed,
    dismiss,
    pin,
    unpin,
    editSchedule,
    startView,
    endView,
  };
}
