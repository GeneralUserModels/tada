import { useEffect, useMemo, useRef, useState } from "react";
import type { RawEvent } from "./data";
import { LABELS, RAW_EVENTS, WIKI_PAGES } from "./data";
import type { Phase, TimelineEvent } from "./timeline";
import { TIMELINE } from "./timeline";

const CHAR_TYPE_MS = 22;

export interface ActiveLabel {
  id: string;
  startedAt: number; // ms since demo start
}

export interface DemoState {
  phase: Phase;
  elapsed: number;

  // Left panel
  rawEventsBySource: Record<string, RawEvent[]>;
  activeLabel: ActiveLabel | null;
  completedLabelIds: Set<string>;

  // Wiki
  createdPages: string[];
  showcasedSlug: string | null;
  showcaseStartedAt: number | null;
  showUpdated: boolean;
  showUnknown: boolean;

  // End-of-timeline handoff — signal to the component to flip interactive on.
  browseRequested: boolean;
}

function initialState(): DemoState {
  return {
    phase: "ingest",
    elapsed: 0,
    rawEventsBySource: { screen: [], email: [], calendar: [], notif: [], filesys: [] },
    activeLabel: null,
    completedLabelIds: new Set(),
    createdPages: [],
    showcasedSlug: null,
    showcaseStartedAt: null,
    showUpdated: false,
    showUnknown: false,
    browseRequested: false,
  };
}

function applyEvent(state: DemoState, ev: TimelineEvent, elapsed: number): DemoState {
  switch (ev.kind) {
    case "phase":
      return { ...state, phase: ev.phase };
    case "rawEvent": {
      const raw = RAW_EVENTS.find((r) => r.id === ev.id);
      if (!raw) return state;
      const lane = state.rawEventsBySource[raw.source] ?? [];
      return {
        ...state,
        rawEventsBySource: {
          ...state.rawEventsBySource,
          [raw.source]: [raw, ...lane].slice(0, 6),
        },
      };
    }
    case "label": {
      const completed = new Set(state.completedLabelIds);
      if (state.activeLabel) completed.add(state.activeLabel.id);
      return {
        ...state,
        activeLabel: { id: ev.id, startedAt: elapsed },
        completedLabelIds: completed,
      };
    }
    case "createPage":
      if (state.createdPages.includes(ev.slug)) return state;
      return { ...state, createdPages: [...state.createdPages, ev.slug] };
    case "showcase":
      return {
        ...state,
        showcasedSlug: ev.slug,
        showcaseStartedAt: elapsed,
        showUpdated: false,
        showUnknown: false,
      };
    case "revealUpdated":
      return { ...state, showUpdated: true };
    case "revealUnknown":
      return { ...state, showUnknown: true };
    case "enterBrowse":
      return { ...state, browseRequested: true };
  }
}

// Fully-built state for the interactive "Browse Dorothy's memex" mode.
function buildInteractiveState(selectedSlug: string): DemoState {
  const rawBySource: Record<string, RawEvent[]> = {
    screen: [], email: [], calendar: [], notif: [], filesys: [],
  };
  for (const ev of RAW_EVENTS) {
    const lane = rawBySource[ev.source] ?? [];
    rawBySource[ev.source] = [ev, ...lane].slice(0, 6);
  }
  return {
    phase: "browse",
    elapsed: 0,
    rawEventsBySource: rawBySource,
    activeLabel: null,
    completedLabelIds: new Set(LABELS.map((l) => l.id)),
    createdPages: Object.keys(WIKI_PAGES).filter((s) => s !== "people/dorothy-gale"),
    showcasedSlug: selectedSlug,
    // A far-past start time forces showcaseProgress() to clamp at 1 — no
    // typing cursors, everything visible instantly.
    showcaseStartedAt: -1e9,
    showUpdated: true,
    showUnknown: true,
    browseRequested: true,
  };
}

export function useTimelineDriver(
  interactive: boolean,
  selectedSlug: string
): DemoState {
  const [state, setState] = useState<DemoState>(initialState);
  const rafRef = useRef<number | null>(null);
  const startRef = useRef<number>(0);
  const eventIdxRef = useRef<number>(0);
  const interactiveRef = useRef(interactive);
  interactiveRef.current = interactive;

  const interactiveState = useMemo(
    () => buildInteractiveState(selectedSlug),
    [selectedSlug]
  );

  // When returning from interactive mode (user clicked Back to the demo),
  // restart the autoplay from the beginning.
  useEffect(() => {
    if (!interactive) {
      startRef.current = performance.now();
      eventIdxRef.current = 0;
      setState(initialState());
    }
  }, [interactive]);

  useEffect(() => {
    startRef.current = performance.now();
    eventIdxRef.current = 0;
    setState(initialState());

    function tick() {
      if (interactiveRef.current) {
        rafRef.current = requestAnimationFrame(tick);
        return;
      }

      const now = performance.now();
      const elapsed = now - startRef.current;

      // Determine event slice OUTSIDE setState — React StrictMode calls the
      // reducer twice in dev, and ref mutation inside would skip events.
      const startIdx = eventIdxRef.current;
      let endIdx = startIdx;
      while (endIdx < TIMELINE.length && TIMELINE[endIdx].at <= elapsed) {
        endIdx++;
      }
      const toApply =
        endIdx > startIdx ? TIMELINE.slice(startIdx, endIdx) : null;
      eventIdxRef.current = endIdx;

      setState((prev) => {
        let next = prev;
        if (toApply) {
          for (const ev of toApply) {
            next = applyEvent(next, ev, elapsed);
          }
        }
        return next.elapsed !== elapsed ? { ...next, elapsed } : next;
      });

      // Once the timeline has emitted enterBrowse, stop ticking. The
      // component will flip `interactive` to true on seeing
      // state.browseRequested, and the interactive static state will render.
      // No loop: the demo intentionally ends in Browse.
      if (eventIdxRef.current < TIMELINE.length) {
        rafRef.current = requestAnimationFrame(tick);
      }
    }

    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
    };
  }, []);

  return interactive ? interactiveState : state;
}

export function labelTypedText(activeLabel: ActiveLabel | null, elapsed: number): { text: string; full: string; done: boolean } | null {
  if (!activeLabel) return null;
  const label = LABELS.find((l) => l.id === activeLabel.id);
  if (!label) return null;
  const dt = Math.max(0, elapsed - activeLabel.startedAt);
  const chars = Math.min(label.text.length, Math.floor(dt / CHAR_TYPE_MS));
  return {
    text: label.text.slice(0, chars),
    full: label.text,
    done: chars >= label.text.length,
  };
}

export function showcaseProgress(state: DemoState): number {
  if (!state.showcaseStartedAt) return 0;
  const dt = state.elapsed - state.showcaseStartedAt;
  // Full progress over 12 seconds.
  return Math.min(1, Math.max(0, dt / 12000));
}

