import React, { useEffect, useState, useRef, useCallback, useMemo } from "react";
import { useAppContext } from "../../context/AppContext";
import { useMoments } from "../../hooks/useMoments";
import { useMomentFeedback } from "../../hooks/useMomentFeedback";
import { ChatView } from "../ChatView";
import { FeatureActivityBanner } from "../FeatureActivityBanner";
import { getServerUrl } from "../../api/client";

const CADENCE_OPTIONS = ["scheduled", "once"] as const;
const REPEAT_OPTIONS = ["daily", "weekly"] as const;
const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"] as const;

const UNCATEGORIZED = "uncategorized";

/** Convert a kebab-case topic slug into a display label. */
function titleizeTopic(s: string): string {
  if (!s) return "Uncategorized";
  return s.split("-").filter(Boolean)
    .map((w) => w[0].toUpperCase() + w.slice(1))
    .join(" ");
}

function TadaDropdown({ value, options, onChange }: { value: string; options: readonly string[]; onChange: (v: string) => void }) {
  const [open, setOpen] = useState(false);
  const [highlighted, setHighlighted] = useState(-1);
  const ref = useRef<HTMLDivElement>(null);

  const select = useCallback((v: string) => { onChange(v); setOpen(false); }, [onChange]);

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") { setOpen(false); return; }
      if (e.key === "ArrowDown") { e.preventDefault(); setHighlighted((h) => Math.min(h + 1, options.length - 1)); }
      if (e.key === "ArrowUp") { e.preventDefault(); setHighlighted((h) => Math.max(h - 1, 0)); }
      if (e.key === "Enter" && highlighted >= 0) { select(options[highlighted]); }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, highlighted, options, select]);

  return (
    <div className="tada-dropdown" ref={ref}>
      <button className="tada-dropdown-trigger" onClick={() => setOpen(!open)} type="button">
        <span>{value}</span>
        <svg width="10" height="10" viewBox="0 0 10 10" fill="none" style={{ transform: open ? "rotate(180deg)" : "none", transition: "transform 0.15s" }}>
          <path d="M2 3.5L5 6.5L8 3.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      </button>
      {open && (
        <>
          <div className="tada-dropdown-backdrop" onClick={() => setOpen(false)} />
          <div className="tada-dropdown-menu">
            {options.map((opt, i) => (
              <div
                key={opt}
                className={`tada-dropdown-item${opt === value ? " selected" : ""}${i === highlighted ? " highlighted" : ""}`}
                onMouseEnter={() => setHighlighted(i)}
                onClick={(e) => { e.stopPropagation(); select(opt); }}
              >
                {opt}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

const HOURS = ["1","2","3","4","5","6","7","8","9","10","11","12"] as const;
const MINUTES = ["00","15","30","45"] as const;
const PERIODS = ["AM","PM"] as const;

function TadaTimePicker({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const [hStr, mStr] = value.split(":");
  let h24 = parseInt(hStr) || 0;
  const m = mStr || "00";
  const period = h24 >= 12 ? "PM" : "AM";
  let h12 = h24 % 12;
  if (h12 === 0) h12 = 12;

  const rebuild = (hour: string, minute: string, p: string) => {
    let h = parseInt(hour);
    if (p === "PM" && h !== 12) h += 12;
    if (p === "AM" && h === 12) h = 0;
    onChange(`${String(h).padStart(2, "0")}:${minute}`);
  };

  // Snap to nearest quarter for display
  const mNum = parseInt(m);
  const snapped = String(Math.round(mNum / 15) * 15 % 60).padStart(2, "0");

  return (
    <div className="tada-time-picker">
      <TadaDropdown value={String(h12)} options={HOURS} onChange={(v) => rebuild(v, snapped, period)} />
      <TadaDropdown value={snapped} options={MINUTES} onChange={(v) => rebuild(String(h12), v, period)} />
      <TadaDropdown value={period} options={PERIODS} onChange={(v) => rebuild(String(h12), snapped, v)} />
    </div>
  );
}

/** Format a date string as relative time or short date. */
function timeAgo(dateStr: string): string {
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const diff = now - then;
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  if (hours < 48) return "Yesterday";
  return new Date(dateStr).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

/** Extract just the time portion from a schedule string like "Monday at 9am" or "at 8am". */
function parseTimeStr(schedule: string): string {
  const m = schedule.match(/(\d{1,2}(?::\d{2})?\s*(?:am|pm))/i);
  return m ? m[1] : "";
}

/** Convert "9am" / "2:30pm" -> "09:00" / "14:30" for <input type="time">. */
function toTime24(s: string): string {
  const m = s.trim().match(/^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$/i);
  if (!m) return "09:00";
  let h = parseInt(m[1]);
  const min = m[2] || "00";
  const ampm = (m[3] || "").toLowerCase();
  if (ampm === "pm" && h !== 12) h += 12;
  if (ampm === "am" && h === 12) h = 0;
  return `${String(h).padStart(2, "0")}:${min}`;
}

/** Convert "14:30" -> "2:30pm", "09:00" -> "9am". */
function fromTime24(t: string): string {
  const [hStr, mStr] = t.split(":");
  let h = parseInt(hStr);
  const min = parseInt(mStr);
  const suffix = h >= 12 ? "pm" : "am";
  if (h === 0) h = 12;
  else if (h > 12) h -= 12;
  return min === 0 ? `${h}${suffix}` : `${h}:${String(min).padStart(2, "0")}${suffix}`;
}

/** Extract the day name from a schedule string like "Monday at 9am". */
function parseDay(schedule: string): string {
  for (const d of DAYS) {
    if (schedule.toLowerCase().includes(d.toLowerCase())) return d;
  }
  return "Monday";
}

/** Build a schedule string from parts. time24 is "HH:mm" format. */
function parseRepeat(schedule: string): string {
  const lower = schedule.toLowerCase();
  if (DAYS.some((d) => lower.includes(d.toLowerCase())) || lower.includes("weekly")) return "weekly";
  return "daily";
}

function buildSchedule(repeat: string, time24: string, day: string): string {
  const friendly = fromTime24(time24);
  if (repeat === "weekly") return `${day} at ${friendly}`;
  return `daily at ${friendly}`;
}

/** Compute progress percent (0-100) from a run activity, or 0 if unknown. */
function activityPercent(activity?: { numTurns: number | null; maxTurns: number | null }): number {
  if (!activity?.maxTurns || activity.maxTurns <= 0 || activity.numTurns == null) return 0;
  return Math.min(100, Math.max(0, (activity.numTurns / activity.maxTurns) * 100));
}

/** Spinner + percent + progress bar for an in-progress moment run. */
function RunningIndicator({ pct }: { pct: number }) {
  return (
    <div className="tada-card-running">
      <div className="tada-card-running-row">
        <div className="feature-activity-spinner" />
        <span className="tada-card-running-text">Running…</span>
        {pct > 0 && <span className="tada-card-running-pct">{Math.round(pct)}%</span>}
      </div>
      {pct > 0 && (
        <div className="feature-activity-progress-track">
          <div className="feature-activity-progress-fill" style={{ width: `${pct}%` }} />
        </div>
      )}
    </div>
  );
}

export function TadaView() {
  const { state } = useAppContext();
  const discoveryActivity = state.agentActivities["moments_discovery"];
  // Each concurrent execution is broadcast as "moment_run:<slug>". Build a
  // per-slug map so we can light up multiple cards / spawn multiple
  // placeholders simultaneously.
  const runActivitiesBySlug = useMemo(() => {
    const out: Record<string, typeof state.agentActivities[string]> = {};
    for (const [k, v] of Object.entries(state.agentActivities)) {
      if (!k.startsWith("moment_run:")) continue;
      if (v.slug) out[v.slug] = v;
    }
    return out;
  }, [state.agentActivities]);
  const runActivities = useMemo(() => Object.values(runActivitiesBySlug), [runActivitiesBySlug]);
  const runningSlugs = useMemo(() => {
    const slugs = new Set<string>();
    for (const act of runActivities) {
      if (act.slug) slugs.add(act.slug);
    }
    return slugs;
  }, [runActivities]);
  const {
    results, loading, load, showDismissed, toggleShowDismissed,
    dismiss, restore, pin, unpin, thumbs, editSchedule, startView, endView, rerun,
    rerunning, rerunFailed,
  } = useMoments();
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null);
  const [resultUrl, setResultUrl] = useState<string | null>(null);
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [editingSlug, setEditingSlug] = useState<string | null>(null);
  const [editCadence, setEditCadence] = useState("");
  const [editRepeat, setEditRepeat] = useState("daily");
  const [editTime, setEditTime] = useState("");
  const [editDay, setEditDay] = useState("Monday");
  const [closedTopics, setClosedTopics] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState("");
  const prevSlugRef = useRef<string | null>(null);
  const feedback = useMomentFeedback(selectedSlug ?? "");

  const isUnread = (r: MomentResult) =>
    !r.dismissed && (!r.last_viewed || new Date(r.completed_at) > new Date(r.last_viewed));

  const visibleResults = useMemo(() => {
    const filtered = results.filter((r) => (showDismissed ? r.dismissed : !r.dismissed));
    const q = query.trim().toLowerCase();
    if (!q) return filtered;
    return filtered.filter((r) =>
      r.title.toLowerCase().includes(q) ||
      r.description.toLowerCase().includes(q) ||
      (r.topic || "").toLowerCase().includes(q),
    );
  }, [results, showDismissed, query]);

  const rawUnreadItems = useMemo(
    () => visibleResults.filter((r) => isUnread(r)),
    [visibleResults], // eslint-disable-line react-hooks/exhaustive-deps
  );
  const runningItems = useMemo(
    () => showDismissed ? [] : visibleResults.filter((r) => runningSlugs.has(r.slug)),
    [showDismissed, visibleResults, runningSlugs],
  );
  const unreadItems = useMemo(
    () => showDismissed
      ? []
      : rawUnreadItems.filter((r) => !runningSlugs.has(r.slug)),
    [showDismissed, rawUnreadItems, runningSlugs],
  );
  const pinnedItems = useMemo(
    () => showDismissed
      ? []
      : visibleResults.filter((r) => r.pinned && !r.dismissed && !runningSlugs.has(r.slug) && !isUnread(r)),
    [showDismissed, visibleResults, runningSlugs], // eslint-disable-line react-hooks/exhaustive-deps
  );
  const topicResults = useMemo(() => {
    if (showDismissed) return visibleResults;
    return visibleResults.filter((r) =>
      !runningSlugs.has(r.slug) &&
      !isUnread(r) &&
      !(r.pinned && !r.dismissed)
    );
  }, [showDismissed, visibleResults, runningSlugs]); // eslint-disable-line react-hooks/exhaustive-deps

  const groupedByTopic = useMemo(() => {
    const out: Record<string, MomentResult[]> = {};
    for (const r of topicResults) {
      const t = r.topic || UNCATEGORIZED;
      (out[t] ??= []).push(r);
    }
    for (const arr of Object.values(out)) {
      arr.sort((a, b) => {
        const aRunning = runActivitiesBySlug[a.slug] ? 1 : 0;
        const bRunning = runActivitiesBySlug[b.slug] ? 1 : 0;
        if (aRunning !== bRunning) return bRunning - aRunning;
        return (b.pinned ? 1 : 0) - (a.pinned ? 1 : 0);
      });
    }
    return out;
  }, [topicResults, runActivitiesBySlug]);

  const topicOrder = useMemo(() => {
    const topics = Object.keys(groupedByTopic);
    topics.sort((a, b) => {
      if (a === UNCATEGORIZED) return 1;
      if (b === UNCATEGORIZED) return -1;
      return a.localeCompare(b);
    });
    return topics;
  }, [groupedByTopic]);

  const toggleTopic = useCallback((t: string) => {
    setClosedTopics((prev) => {
      const next = new Set(prev);
      if (next.has(t)) next.delete(t);
      else next.add(t);
      return next;
    });
  }, []);

  const jumpToChapter = useCallback((key: string) => {
    setClosedTopics((prev) => {
      if (!prev.has(key)) return prev;
      const next = new Set(prev);
      next.delete(key);
      return next;
    });
    requestAnimationFrame(() => {
      const el = document.getElementById(`tada-chapter-${key}`);
      if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }, []);

  const placeholderActivities = useMemo(() => {
    if (loading) return [];
    return runActivities.filter((act) => {
      if (!act.slug) return false;
      return !results.some((r) => r.slug === act.slug);
    });
  }, [runActivities, results, loading]);

  useEffect(() => {
    if (state.connected) load();
  }, [state.connected, load]);

  // Track view time: end previous view when slug changes, start new one
  useEffect(() => {
    if (prevSlugRef.current && prevSlugRef.current !== selectedSlug) {
      endView(prevSlugRef.current);
    }
    if (selectedSlug) {
      startView(selectedSlug);
    }
    prevSlugRef.current = selectedSlug;
    return () => {
      if (prevSlugRef.current) {
        endView(prevSlugRef.current);
        prevSlugRef.current = null;
      }
    };
  }, [selectedSlug]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleCardClick = (slug: string, openFeedback = false) => {
    setSelectedSlug(slug);
    setResultUrl(`${getServerUrl()}/api/moments/results/${slug}/index.html`);
    setFeedbackOpen(openFeedback);
  };

  const handleBack = () => {
    if (feedback.active) feedback.endConversation();
    setSelectedSlug(null);
    setResultUrl(null);
    setFeedbackOpen(false);
  };

  const handleEndFeedback = async () => {
    await feedback.endConversation();
    feedback.setMessages([]);
    setFeedbackOpen(false);
    load(); // reload to update has_feedback status
  };

  const handleFeedbackSend = (content: string) => {
    if (!feedback.active) {
      // First message — start the conversation
      feedback.startConversation(content);
    } else {
      feedback.sendMessage(content);
    }
  };

  const openScheduleEditor = (e: React.MouseEvent, r: MomentResult) => {
    e.stopPropagation();
    if (effectiveCadence(r) === "trigger") return;
    const sched = r.schedule_override || r.schedule;
    setEditingSlug(r.slug);
    setEditCadence(effectiveCadence(r));
    setEditRepeat(parseRepeat(sched));
    setEditTime(toTime24(parseTimeStr(sched)));
    setEditDay(parseDay(sched));
  };

  const saveSchedule = async () => {
    if (!editingSlug) return;
    if (editCadence === "scheduled" && !editTime) return;
    const schedule = editCadence === "scheduled" ? buildSchedule(editRepeat, editTime, editDay) : "";
    await editSchedule(editingSlug, editCadence, schedule);
    setEditingSlug(null);
  };

  const displayTime = (r: MomentResult) => parseTimeStr(r.schedule_override || r.schedule);
  const effectiveCadence = (r: MomentResult) => r.cadence_override || r.cadence;

  // Detail view
  if (selectedSlug && resultUrl) {
    const selected = results.find((r) => r.slug === selectedSlug);
    return (
      <div id="tada-view" className="view active">
        <div className="tada-detail-header glass-card">
          <button className="tada-back-btn" onClick={handleBack}>
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M9 2L4 7l5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            Back
          </button>
          {selected && (
            <>
              <span className="tada-detail-title">{selected.title}</span>
              {rerunFailed.has(selected.slug) && <span className="tada-rerun-failed-badge">Rerun failed</span>}
              <div className="tada-card-actions">
                <button
                  className={`tada-card-action-btn${rerunning.has(selected.slug) ? " rerunning" : ""}`}
                  title={rerunning.has(selected.slug) ? "Rerunning\u2026" : "Re-run"}
                  onClick={() => rerun(selected.slug)}
                  disabled={rerunning.has(selected.slug)}
                >
                  <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                    <path d="M2 8a6 6 0 0110.47-4M14 8a6 6 0 01-10.47 4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
                    <path d="M12 1v3.5h-3.5M4 15v-3.5h3.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </button>
                <button
                  className={`tada-card-action-btn${feedbackOpen ? " active" : ""}`}
                  title="Give feedback"
                  onClick={() => setFeedbackOpen(!feedbackOpen)}
                >
                  <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                    <path d="M2 3h12v8H5l-3 3V3z" stroke="currentColor" fill={feedbackOpen ? "currentColor" : "none"} strokeWidth="1.3" strokeLinejoin="round"/>
                  </svg>
                </button>
                <button
                  className={`tada-card-action-btn tada-thumbs-up${selected.thumbs === "up" ? " active" : ""}`}
                  title="Thumbs up"
                  onClick={() => thumbs(selected.slug, "up")}
                >
                  <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                    <path d="M5 14V7m0 7H3.5A1.5 1.5 0 012 12.5v-4A1.5 1.5 0 013.5 7H5m0 7h5.59a2 2 0 001.96-1.61l.86-4.28A1.5 1.5 0 0011.93 6H9V3.5A1.5 1.5 0 007.5 2L5 7"
                      stroke="currentColor" fill={selected.thumbs === "up" ? "currentColor" : "none"} strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </button>
                <button
                  className={`tada-card-action-btn tada-thumbs-down${selected.thumbs === "down" ? " active" : ""}`}
                  title="Thumbs down"
                  onClick={() => thumbs(selected.slug, "down")}
                >
                  <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                    <path d="M11 2v7m0-7h1.5A1.5 1.5 0 0114 3.5v4a1.5 1.5 0 01-1.5 1.5H11m0-7H5.41a2 2 0 00-1.96 1.61l-.86 4.28A1.5 1.5 0 004.07 10H7v2.5A1.5 1.5 0 008.5 14L11 9"
                      stroke="currentColor" fill={selected.thumbs === "down" ? "currentColor" : "none"} strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </button>
                {selected.dismissed ? (
                  <button
                    className="tada-card-action-btn"
                    title="Restore"
                    onClick={() => restore(selected.slug)}
                  >
                    <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                      <path d="M3 8.5V11h2.5M3 11l3.5-3.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
                      <path d="M6.5 3H11v4.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                  </button>
                ) : (
                  <>
                    <button
                      className={`tada-card-action-btn${selected.pinned ? " active" : ""}`}
                      title={selected.pinned ? "Unpin" : "Pin"}
                      onClick={() => selected.pinned ? unpin(selected.slug) : pin(selected.slug)}
                    >
                      <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                        <path d="M7.5 1.5L10.5 4.5L9 8L10.5 12.5L7 9L3.5 12.5L5 8L3.5 4.5L6.5 1.5L7.5 1.5Z"
                          stroke="currentColor" fill={selected.pinned ? "currentColor" : "none"} strokeWidth="1" strokeLinejoin="round"/>
                      </svg>
                    </button>
                    <button
                      className="tada-card-action-btn"
                      title="Dismiss"
                      onClick={() => { dismiss(selected.slug); handleBack(); }}
                    >
                      <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                        <path d="M3 3l8 8M11 3l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                      </svg>
                    </button>
                  </>
                )}
              </div>
            </>
          )}
        </div>
        <div className={`tada-detail-split${feedbackOpen ? "" : " tada-detail-split--full"}`}>
          <div className="tada-detail glass-card">
            <iframe
              src={resultUrl}
              sandbox="allow-scripts allow-popups allow-popups-to-escape-sandbox"
              style={{ width: "100%", height: "100%", border: "none", borderRadius: "var(--r-md)" }}
            />
          </div>
          {feedbackOpen && (
            <div className="tada-feedback-panel glass-card">
              <ChatView
                messages={feedback.messages}
                streaming={feedback.streaming}
                active={true}
                onSend={handleFeedbackSend}
                onEnd={handleEndFeedback}
                placeholder="Share your feedback..."
              />
            </div>
          )}
        </div>
      </div>
    );
  }

  // List view
  const totalTadas = visibleResults.length;
  const totalUnread = rawUnreadItems.length;
  const totalRunning = showDismissed ? 0 : runningItems.length + placeholderActivities.length;
  const todayLabel = new Date().toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" });

  return (
    <div id="tada-view" className="view active tada-list">
      {discoveryActivity && (
        <FeatureActivityBanner activity={discoveryActivity} label="Discovery" />
      )}

      <header className="tada-masthead">
        <div className="tada-masthead-meta">
          <span className="tada-masthead-eyebrow">{todayLabel}</span>
          <span className="tada-masthead-sep" aria-hidden="true">·</span>
          <span className="tada-masthead-count">
            {totalTadas} {totalTadas === 1 ? (showDismissed ? "dismissed" : "tada") : (showDismissed ? "dismissed" : "tadas")}
          </span>
          {!showDismissed && totalUnread > 0 && (
            <>
              <span className="tada-masthead-sep" aria-hidden="true">·</span>
              <span className="tada-masthead-count tada-masthead-count--unread">
                <span className="tada-unread-pip" />
                {totalUnread} unread
              </span>
            </>
          )}
        </div>
        <div className="tada-masthead-lead">
          <div className="tada-masthead-search">
            <svg className="tada-masthead-search-icon" width="14" height="14" viewBox="0 0 14 14" fill="none">
              <circle cx="6" cy="6" r="4.25" stroke="currentColor" strokeWidth="1.3"/>
              <path d="M9.2 9.2L12 12" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
            </svg>
            <input
              type="text"
              className="tada-masthead-search-input"
              placeholder={showDismissed ? "Search dismissed tadas…" : "Search tadas…"}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              spellCheck={false}
              autoCorrect="off"
            />
            {query && (
              <button
                type="button"
                className="tada-masthead-search-clear"
                onClick={() => setQuery("")}
                title="Clear search"
              >
                <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                  <path d="M2 2l6 6M8 2l-6 6" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/>
                </svg>
              </button>
            )}
          </div>
          <button className="tada-masthead-link" onClick={toggleShowDismissed} type="button">
            {showDismissed ? "Show active" : "Show dismissed"}
          </button>
        </div>
      </header>

      <div className="tada-list-body">
        <main className="tada-list-main">
          {loading ? (
            <div className="tada-empty">
              <div className="tada-spinner" />
              <span className="tada-empty-line">Loading tadas…</span>
            </div>
          ) : topicOrder.length === 0 && totalRunning === 0 && unreadItems.length === 0 && pinnedItems.length === 0 ? (
            query.trim() ? (
              <div className="tada-empty">
                <span className="tada-empty-line">No matches for "{query.trim()}"</span>
                <span className="tada-empty-hint">Try a different search, or clear the field to see everything.</span>
              </div>
            ) : (
              <div className="tada-empty">
                <svg className="tada-empty-icon" width="32" height="32" viewBox="0 0 32 32" fill="none">
                  <path d="M16 4l3.09 6.26L26 11.27l-5 4.87 1.18 6.88L16 19.77l-6.18 3.25L11 16.14l-5-4.87 6.91-1.01L16 4z"
                    stroke="var(--sage)" strokeWidth="1.5" strokeLinejoin="round" fill="rgba(var(--sage-rgb), 0.08)"/>
                </svg>
                <span className="tada-empty-line">
                  {showDismissed ? "No dismissed tadas" : "No tadas yet"}
                </span>
                <span className="tada-empty-hint">
                  {showDismissed
                    ? "Anything you set aside will rest here."
                    : "Completed tadas will arrive here as they run on schedule."}
                </span>
              </div>
            )
          ) : (
            <>
              {!showDismissed && totalRunning > 0 && (
                <section
                  id="tada-chapter-__running"
                  className={`tada-chapter tada-chapter--running${closedTopics.has("__running") ? "" : " open"}${runningItems.some(isUnread) ? " has-unread" : ""}`}
                >
                  <button className="tada-chapter-header" onClick={() => toggleTopic("__running")} type="button">
                    <span className="tada-chapter-name">
                      <span className="tada-chapter-glyph tada-chapter-glyph--running" />
                      Running
                      <span className="tada-chapter-count">{totalRunning}</span>
                    </span>
                    <svg className="tada-chapter-caret" width="9" height="9" viewBox="0 0 10 10" fill="none">
                      <path d="M3.5 2L7 5L3.5 8" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                  </button>
                  {!closedTopics.has("__running") && (
                    <div className="tada-chapter-body">
                      {placeholderActivities.map((act, i) => (
                        <article
                          key={`placeholder-${act.slug}`}
                          className="glass-card tada-entry tada-entry--running"
                          style={{ animationDelay: `${i * 0.04}s` }}
                        >
                          <div className="tada-card-header">
                            <h3 className="tada-card-title">{act.message.replace(/^Running:\s*/, "")}</h3>
                          </div>
                          <RunningIndicator pct={activityPercent(act)} />
                        </article>
                      ))}
                      {runningItems.map((r, i) => renderEntry(r, i + placeholderActivities.length))}
                    </div>
                  )}
                </section>
              )}
              {!showDismissed && unreadItems.length > 0 && (
                <ChapterSection
                  keyName="__unread"
                  label="Unread"
                  variant="unread"
                  items={unreadItems}
                  isOpen={!closedTopics.has("__unread")}
                  onToggle={() => toggleTopic("__unread")}
                  renderEntry={renderEntry}
                  isUnreadFn={isUnread}
                />
              )}
              {!showDismissed && pinnedItems.length > 0 && (
                <ChapterSection
                  keyName="__pinned"
                  label="Pinned"
                  variant="pinned"
                  items={pinnedItems}
                  isOpen={!closedTopics.has("__pinned")}
                  onToggle={() => toggleTopic("__pinned")}
                  renderEntry={renderEntry}
                  isUnreadFn={isUnread}
                />
              )}
              {topicOrder.map((topic) => {
                const items = groupedByTopic[topic];
                const isOpen = !closedTopics.has(topic);
                const unreadCount = items.filter(isUnread).length;
                return (
                  <ChapterSection
                    key={topic}
                    keyName={topic}
                    label={titleizeTopic(topic)}
                    items={items}
                    isOpen={isOpen}
                    unreadCount={unreadCount}
                    onToggle={() => toggleTopic(topic)}
                    renderEntry={renderEntry}
                    isUnreadFn={isUnread}
                  />
                );
              })}
            </>
          )}
          <div style={{ minHeight: 24, flexShrink: 0 }} />
        </main>

        {!loading && (topicOrder.length > 0 || (!showDismissed && (totalRunning > 0 || pinnedItems.length > 0 || unreadItems.length > 0))) && (
          <aside className="tada-toc" aria-label="Jump to section">
            <div className="tada-toc-label">Jump to</div>
            {!showDismissed && totalRunning > 0 && (
              <button
                type="button"
                className="tada-toc-item tada-toc-item--running"
                onClick={() => jumpToChapter("__running")}
              >
                <span className="tada-toc-item-glyph tada-toc-item-glyph--running" />
                <span className="tada-toc-item-name">Running</span>
                <span className="tada-toc-item-count">{totalRunning}</span>
              </button>
            )}
            {!showDismissed && unreadItems.length > 0 && (
              <button
                type="button"
                className="tada-toc-item tada-toc-item--unread"
                onClick={() => jumpToChapter("__unread")}
              >
                <span className="tada-toc-item-glyph tada-toc-item-glyph--dot" />
                <span className="tada-toc-item-name">Unread</span>
                <span className="tada-toc-item-count">{unreadItems.length}</span>
              </button>
            )}
            {!showDismissed && pinnedItems.length > 0 && (
              <button
                type="button"
                className="tada-toc-item tada-toc-item--pinned"
                onClick={() => jumpToChapter("__pinned")}
              >
                <svg className="tada-toc-item-glyph" width="9" height="9" viewBox="0 0 14 14" fill="none">
                  <path d="M7.5 1.5L10.5 4.5L9 8L10.5 12.5L7 9L3.5 12.5L5 8L3.5 4.5L6.5 1.5L7.5 1.5Z"
                    stroke="currentColor" fill="currentColor" strokeWidth="1" strokeLinejoin="round"/>
                </svg>
                <span className="tada-toc-item-name">Pinned</span>
                <span className="tada-toc-item-count">{pinnedItems.length}</span>
              </button>
            )}
            {(totalRunning > 0 || unreadItems.length > 0 || pinnedItems.length > 0) && topicOrder.length > 0 && (
              <div className="tada-toc-divider" aria-hidden="true" />
            )}
            {topicOrder.map((topic) => (
              <button
                key={topic}
                type="button"
                className="tada-toc-item"
                onClick={() => jumpToChapter(topic)}
              >
                <span className="tada-toc-item-name">{titleizeTopic(topic)}</span>
                <span className="tada-toc-item-count">{groupedByTopic[topic].length}</span>
              </button>
            ))}
          </aside>
        )}
      </div>
    </div>
  );

  function renderEntry(r: MomentResult, i: number) {
          const slugActivity = runActivitiesBySlug[r.slug];
          const isRunning = !!slugActivity;
          const cardUnread = isUnread(r);
          const runPct = isRunning ? activityPercent(slugActivity) : 0;
          const isLead = i === 0 && !r.dismissed;
          return (
          <article
            key={r.slug}
            className={`glass-card tada-entry${isLead ? " tada-entry--lead" : ""}${r.pinned ? " tada-entry--pinned" : ""}${r.dismissed ? " tada-entry--dismissed" : ""}${rerunning.has(r.slug) ? " tada-entry--rerunning" : ""}${isRunning ? " tada-entry--running" : ""}${cardUnread ? " tada-entry--unread" : ""}`}
            style={{ animationDelay: `${i * 0.04}s` }}
            onClick={isRunning ? undefined : () => handleCardClick(r.slug)}
          >
            <div className="tada-card-header">
              <h3 className="tada-card-title">
                {r.pinned && (
                  <svg className="tada-pin-indicator" width="12" height="12" viewBox="0 0 14 14" fill="none" style={{ marginRight: 4, verticalAlign: -1 }}>
                    <path d="M7.5 1.5L10.5 4.5L9 8L10.5 12.5L7 9L3.5 12.5L5 8L3.5 4.5L6.5 1.5L7.5 1.5Z"
                      stroke="var(--sage)" fill="var(--sage)" strokeWidth="1" strokeLinejoin="round"/>
                  </svg>
                )}
                <span className="tada-card-title-text">{r.title}</span>
                {r.dismissed && <span className="tada-dismissed-badge">Dismissed</span>}
                {rerunFailed.has(r.slug) && <span className="tada-rerun-failed-badge">Rerun failed</span>}
              </h3>
            </div>
            <div className="tada-card-schedule tada-card-schedule--clickable" onClick={(e) => openScheduleEditor(e, r)}>
              <span className="tada-card-frequency" data-freq={effectiveCadence(r)}>
                <span className="tada-card-frequency-dot" aria-hidden="true" />
                {effectiveCadence(r)}
              </span>
              {effectiveCadence(r) === "scheduled" && (
                <span className="tada-card-time">{displayTime(r)}</span>
              )}
              <span className="tada-card-date">{timeAgo(r.completed_at)}</span>
            </div>
            <p className="tada-card-desc">{r.description}</p>

            {editingSlug === r.slug && (
              <div className="tada-schedule-editor" onClick={(e) => e.stopPropagation()}>
                <div className="tada-schedule-editor-row">
                  <div className="tada-schedule-field">
                    <span>Cadence</span>
                    <TadaDropdown value={editCadence} options={CADENCE_OPTIONS} onChange={setEditCadence} />
                  </div>
                  {editCadence === "scheduled" && (
                    <div className="tada-schedule-field">
                      <span>Repeat</span>
                      <TadaDropdown value={editRepeat} options={REPEAT_OPTIONS} onChange={setEditRepeat} />
                    </div>
                  )}
                  {editCadence === "scheduled" && editRepeat === "weekly" && (
                    <div className="tada-schedule-field">
                      <span>Day</span>
                      <TadaDropdown value={editDay} options={DAYS} onChange={setEditDay} />
                    </div>
                  )}
                  {editCadence === "scheduled" && (
                    <div className="tada-schedule-field">
                      <span>Time</span>
                      <TadaTimePicker value={editTime} onChange={setEditTime} />
                    </div>
                  )}
                </div>
                <div className="tada-schedule-editor-actions">
                  <button className="tada-schedule-save" onClick={saveSchedule}>Save</button>
                  <button className="tada-schedule-cancel" onClick={() => setEditingSlug(null)}>Cancel</button>
                </div>
              </div>
            )}

            {isRunning && <RunningIndicator pct={runPct} />}

            <div className="tada-card-footer" onClick={(e) => e.stopPropagation()}>
              <div className="tada-card-actions">
                <button
                  className={`tada-card-action-btn${rerunning.has(r.slug) ? " rerunning" : ""}`}
                  title={rerunning.has(r.slug) ? "Rerunning\u2026" : "Re-run"}
                  onClick={() => rerun(r.slug)}
                  disabled={rerunning.has(r.slug)}
                >
                  <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
                    <path d="M2 8a6 6 0 0110.47-4M14 8a6 6 0 01-10.47 4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
                    <path d="M12 1v3.5h-3.5M4 15v-3.5h3.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </button>
                <button
                  className="tada-card-action-btn"
                  title="Give feedback"
                  onClick={() => handleCardClick(r.slug, true)}
                >
                  <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
                    <path d="M2 3h12v8H5l-3 3V3z" stroke="currentColor" fill="none" strokeWidth="1.3" strokeLinejoin="round"/>
                  </svg>
                </button>
                <button
                  className={`tada-card-action-btn tada-thumbs-up${r.thumbs === "up" ? " active" : ""}`}
                  title="Thumbs up"
                  onClick={() => thumbs(r.slug, "up")}
                >
                  <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
                    <path d="M5 14V7m0 7H3.5A1.5 1.5 0 012 12.5v-4A1.5 1.5 0 013.5 7H5m0 7h5.59a2 2 0 001.96-1.61l.86-4.28A1.5 1.5 0 0011.93 6H9V3.5A1.5 1.5 0 007.5 2L5 7"
                      stroke="currentColor" fill={r.thumbs === "up" ? "currentColor" : "none"} strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </button>
                <button
                  className={`tada-card-action-btn tada-thumbs-down${r.thumbs === "down" ? " active" : ""}`}
                  title="Thumbs down"
                  onClick={() => thumbs(r.slug, "down")}
                >
                  <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
                    <path d="M11 2v7m0-7h1.5A1.5 1.5 0 0114 3.5v4a1.5 1.5 0 01-1.5 1.5H11m0-7H5.41a2 2 0 00-1.96 1.61l-.86 4.28A1.5 1.5 0 004.07 10H7v2.5A1.5 1.5 0 008.5 14L11 9"
                      stroke="currentColor" fill={r.thumbs === "down" ? "currentColor" : "none"} strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </button>
                {r.dismissed ? (
                  <button
                    className="tada-card-action-btn"
                    title="Restore"
                    onClick={() => restore(r.slug)}
                  >
                    <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
                      <path d="M3 8.5V11h2.5M3 11l3.5-3.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
                      <path d="M6.5 3H11v4.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                  </button>
                ) : (
                  <>
                    <button
                      className={`tada-card-action-btn${r.pinned ? " active" : ""}`}
                      title={r.pinned ? "Unpin" : "Pin"}
                      onClick={() => r.pinned ? unpin(r.slug) : pin(r.slug)}
                    >
                      <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
                        <path d="M7.5 1.5L10.5 4.5L9 8L10.5 12.5L7 9L3.5 12.5L5 8L3.5 4.5L6.5 1.5L7.5 1.5Z"
                          stroke="currentColor" fill={r.pinned ? "currentColor" : "none"} strokeWidth="1" strokeLinejoin="round"/>
                      </svg>
                    </button>
                    <button
                      className="tada-card-action-btn"
                      title="Dismiss"
                      onClick={() => dismiss(r.slug)}
                    >
                      <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
                        <path d="M3 3l8 8M11 3l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                      </svg>
                    </button>
                  </>
                )}
              </div>
            </div>
          </article>
          );
  }
}

interface ChapterSectionProps {
  keyName: string;
  label: string;
  items: MomentResult[];
  isOpen: boolean;
  unreadCount?: number;
  variant?: "pinned" | "unread" | "topic";
  onToggle: () => void;
  renderEntry: (r: MomentResult, i: number) => JSX.Element;
  isUnreadFn: (r: MomentResult) => boolean;
}

function ChapterSection({ keyName, label, items, isOpen, unreadCount, variant = "topic", onToggle, renderEntry, isUnreadFn }: ChapterSectionProps) {
  const computedUnread = unreadCount ?? items.filter(isUnreadFn).length;
  return (
    <section
      key={keyName}
      id={`tada-chapter-${keyName}`}
      className={`tada-chapter tada-chapter--${variant}${isOpen ? " open" : ""}${computedUnread > 0 ? " has-unread" : ""}`}
    >
      <button className="tada-chapter-header" onClick={onToggle} type="button">
        <span className="tada-chapter-name">
          {variant === "pinned" && (
            <svg className="tada-chapter-glyph" width="10" height="10" viewBox="0 0 14 14" fill="none">
              <path d="M7.5 1.5L10.5 4.5L9 8L10.5 12.5L7 9L3.5 12.5L5 8L3.5 4.5L6.5 1.5L7.5 1.5Z"
                stroke="currentColor" fill="currentColor" strokeWidth="1" strokeLinejoin="round"/>
            </svg>
          )}
          {variant === "unread" && <span className="tada-chapter-glyph tada-chapter-glyph--dot" />}
          {label}
          <span className="tada-chapter-count">{items.length}</span>
          {variant === "topic" && computedUnread > 0 && (
            <span className="tada-chapter-unread">{computedUnread} new</span>
          )}
        </span>
        <svg className="tada-chapter-caret" width="9" height="9" viewBox="0 0 10 10" fill="none">
          <path d="M3.5 2L7 5L3.5 8" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      </button>
      {isOpen && (
        <div className="tada-chapter-body">
          {items.map((r, i) => renderEntry(r, i))}
        </div>
      )}
    </section>
  );
}
