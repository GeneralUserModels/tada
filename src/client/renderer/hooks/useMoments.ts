import { useState, useCallback, useEffect, useRef } from "react";
import {
  getMomentsResults,
  updateMomentState,
  updateMomentSchedule,
  recordMomentView,
  recordMomentViewEnd,
  rerunMoment,
} from "../api/client";
import { on as sseOn } from "../api/sse";

function deleteFromSet(prev: Set<string>, slug: string): Set<string> {
  const next = new Set(prev);
  next.delete(slug);
  return next;
}

// Module-level set so rerunning state survives component unmount/remount
const _rerunning = new Set<string>();

// Register SSE listeners once at module level so they always update _rerunning
let _sseInitialized = false;
const _sseSubscribers = new Set<() => void>();

function _initSSE() {
  if (_sseInitialized) return;
  _sseInitialized = true;

  sseOn("moment_completed", (data) => {
    const slug = (data as { slug?: string }).slug;
    if (slug) _rerunning.delete(slug);
    _sseSubscribers.forEach((cb) => cb());
  });

  sseOn("moment_rerun_failed", (data) => {
    const slug = (data as { slug?: string }).slug;
    if (slug) _rerunning.delete(slug);
    _sseSubscribers.forEach((cb) => cb());
  });
}

export function useMoments() {
  const [results, setResults] = useState<MomentResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [showDismissed, setShowDismissed] = useState(false);
  const [rerunning, setRerunning] = useState<Set<string>>(() => new Set(_rerunning));
  const [rerunFailed, setRerunFailed] = useState<Set<string>>(new Set());
  const viewStartRef = useRef<{ slug: string; ts: number } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    const res = await getMomentsResults(showDismissed);
    setResults(res);
    setLoading(false);
  }, [showDismissed]);

  // Sync from module-level _rerunning and handle SSE events
  useEffect(() => {
    _initSSE();

    const sync = () => {
      setRerunning(new Set(_rerunning));
      load();
    };
    _sseSubscribers.add(sync);
    return () => { _sseSubscribers.delete(sync); };
  }, [load]);

  // Handle rerun failed SSE — separate listener for the transient badge
  useEffect(() => {
    sseOn("moment_rerun_failed", (data) => {
      const slug = (data as { slug?: string }).slug;
      if (slug) {
        setRerunFailed((prev) => new Set(prev).add(slug));
        setTimeout(() => setRerunFailed((prev) => deleteFromSet(prev, slug)), 8000);
      }
    });
  }, []);

  const dismiss = useCallback(async (slug: string) => {
    setResults((prev) => prev.filter((r) => r.slug !== slug));
    await updateMomentState(slug, { dismissed: true });
  }, []);

  const restore = useCallback(async (slug: string) => {
    setResults((prev) =>
      prev.map((r) => (r.slug === slug ? { ...r, dismissed: false } : r))
    );
    await updateMomentState(slug, { dismissed: false });
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

  const thumbs = useCallback(async (slug: string, value: "up" | "down") => {
    setResults((prev) =>
      prev.map((r) =>
        r.slug === slug ? { ...r, thumbs: r.thumbs === value ? null : value } : r
      )
    );
    const current = results.find((r) => r.slug === slug);
    const newValue = current?.thumbs === value ? null : value;
    await updateMomentState(slug, { thumbs: newValue });
  }, [results]);

  const editSchedule = useCallback(async (slug: string, cadence: string, schedule: string) => {
    await updateMomentSchedule(slug, { cadence, schedule });
    setResults((prev) =>
      prev.map((r) =>
        r.slug === slug ? { ...r, cadence_override: cadence, schedule_override: schedule } : r
      )
    );
  }, []);


  const startView = useCallback((slug: string) => {
    viewStartRef.current = { slug, ts: Date.now() };
    setResults((prev) =>
      prev.map((r) =>
        r.slug === slug ? { ...r, last_viewed: new Date().toISOString() } : r
      )
    );
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

  const rerun = useCallback(async (slug: string) => {
    _rerunning.add(slug);
    setRerunning(new Set(_rerunning));
    try {
      await rerunMoment(slug);
      // 202 accepted — execution runs in background.
      // SSE events (moment_completed / moment_rerun_failed) will clear state.
    } catch {
      // 404/409/network error — rerun didn't start
      _rerunning.delete(slug);
      setRerunning(new Set(_rerunning));
      setRerunFailed((prev) => new Set(prev).add(slug));
      setTimeout(() => setRerunFailed((prev) => deleteFromSet(prev, slug)), 8000);
    }
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
    restore,
    pin,
    unpin,
    thumbs,
    editSchedule,
    startView,
    endView,
    rerun,
    rerunning,
    rerunFailed,
  };
}
