import React, { useEffect, useState, useRef, useCallback, useMemo } from "react";
import { useAppContext } from "../../context/AppContext";
import { useMoments } from "../../hooks/useMoments";
import { useMomentFeedback } from "../../hooks/useMomentFeedback";
import { ChatView } from "../ChatView";
import { FeatureActivityBanner } from "../FeatureActivityBanner";
import { getServerUrl } from "../../api/client";

type TadaTab = "one-off" | "recurring";

const FREQUENCY_OPTIONS = ["daily", "weekly", "once"] as const;
const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"] as const;

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
function buildSchedule(frequency: string, time24: string, day: string): string {
  const friendly = fromTime24(time24);
  if (frequency === "weekly") return `${day} at ${friendly}`;
  return `at ${friendly}`;
}

export function TadaView() {
  const { state } = useAppContext();
  const discoveryActivity = state.agentActivities["moments_discovery"];
  const runActivity = state.agentActivities["moment_run"];
  const {
    results, loading, load, showDismissed, toggleShowDismissed,
    dismiss, restore, pin, unpin, thumbs, editSchedule, startView, endView, rerun,
    rerunning, rerunFailed,
  } = useMoments();
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null);
  const [resultUrl, setResultUrl] = useState<string | null>(null);
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [editingSlug, setEditingSlug] = useState<string | null>(null);
  const [editFreq, setEditFreq] = useState("");
  const [editTime, setEditTime] = useState("");
  const [editDay, setEditDay] = useState("Monday");
  const [tab, setTab] = useState<TadaTab>("one-off");
  const prevSlugRef = useRef<string | null>(null);
  const feedback = useMomentFeedback(selectedSlug ?? "");

  const isOneOff = (r: MomentResult) => (r.frequency_override || r.frequency) === "once";
  const isUnread = (r: MomentResult) =>
    !r.dismissed && (!r.last_viewed || new Date(r.completed_at) > new Date(r.last_viewed));

  const oneOffResults = useMemo(() => results.filter(isOneOff), [results]);
  const recurringResults = useMemo(() => results.filter((r) => !isOneOff(r)), [results]);
  const oneOffUnread = useMemo(() => oneOffResults.filter(isUnread).length, [oneOffResults]);
  const recurringUnread = useMemo(() => recurringResults.filter(isUnread).length, [recurringResults]);
  const tabResults = tab === "one-off" ? oneOffResults : recurringResults;

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
    const sched = r.schedule_override || r.schedule;
    setEditingSlug(r.slug);
    setEditFreq(r.frequency_override || r.frequency);
    setEditTime(toTime24(parseTimeStr(sched)));
    setEditDay(parseDay(sched));
  };

  const saveSchedule = async () => {
    if (!editingSlug) return;
    if (editFreq !== "once" && !editTime) return;
    const schedule = editFreq === "once" ? "" : buildSchedule(editFreq, editTime, editDay);
    await editSchedule(editingSlug, editFreq, schedule);
    setEditingSlug(null);
  };

  const displayTime = (r: MomentResult) => parseTimeStr(r.schedule_override || r.schedule);
  const effectiveFrequency = (r: MomentResult) => r.frequency_override || r.frequency;

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
  return (
    <div id="tada-view" className="view active">
      {discoveryActivity && (
        <FeatureActivityBanner activity={discoveryActivity} label="Discovery" />
      )}
      <div className="tada-tab-bar">
        <div className="tada-tab-pills">
          <button
            className={`tada-tab${tab === "one-off" ? " active" : ""}`}
            onClick={() => setTab("one-off")}
          >
            One-off{oneOffUnread > 0 && <span className="tada-tab-badge">{oneOffUnread}</span>}
          </button>
          <button
            className={`tada-tab${tab === "recurring" ? " active" : ""}`}
            onClick={() => setTab("recurring")}
          >
            Recurring{recurringUnread > 0 && <span className="tada-tab-badge">{recurringUnread}</span>}
          </button>
        </div>
        <button className="tada-show-dismissed" onClick={toggleShowDismissed}>
          {showDismissed ? "Hide dismissed" : "Show dismissed"}
        </button>
      </div>

      {/* Placeholder card for a moment that's running but has no completed result yet */}
      {runActivity?.slug && !loading && !results.some((r) => r.slug === runActivity.slug) && (() => {
        const pct = runActivity.maxTurns && runActivity.maxTurns > 0 && runActivity.numTurns != null
          ? Math.min(100, Math.max(0, (runActivity.numTurns / runActivity.maxTurns) * 100)) : 0;
        return (
          <section className="glass-card tada-card tada-card--running">
            <div className="tada-card-header">
              <h3 className="tada-card-title">{runActivity.message.replace(/^Running:\s*/, "")}</h3>
            </div>
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
          </section>
        );
      })()}

      {loading ? (
        <div className="tada-empty-state">
          <div className="tada-spinner" />
          <span>Loading moments...</span>
        </div>
      ) : tabResults.length === 0 && !runActivity ? (
        <div className="tada-empty-state">
          <svg className="tada-empty-icon" width="32" height="32" viewBox="0 0 32 32" fill="none">
            <path d="M16 4l3.09 6.26L26 11.27l-5 4.87 1.18 6.88L16 19.77l-6.18 3.25L11 16.14l-5-4.87 6.91-1.01L16 4z"
              stroke="var(--sage)" strokeWidth="1.5" strokeLinejoin="round" fill="rgba(var(--sage-rgb), 0.08)"/>
          </svg>
          <span>No {tab === "one-off" ? "one-off" : "recurring"} moments yet</span>
          <span className="tada-empty-hint">Completed moments will appear here as they run on schedule.</span>
        </div>
      ) : (
        tabResults.filter((r) => showDismissed ? r.dismissed : !r.dismissed).sort((a, b) => {
          const aRunning = runActivity?.slug === a.slug ? 1 : 0;
          const bRunning = runActivity?.slug === b.slug ? 1 : 0;
          if (aRunning !== bRunning) return bRunning - aRunning;
          return (b.pinned ? 1 : 0) - (a.pinned ? 1 : 0);
        }).map((r, i) => {
          const isRunning = runActivity?.slug === r.slug;
          const cardUnread = isUnread(r);
          const runPct = isRunning && runActivity.maxTurns && runActivity.maxTurns > 0 && runActivity.numTurns != null
            ? Math.min(100, Math.max(0, (runActivity.numTurns / runActivity.maxTurns) * 100))
            : 0;
          return (
          <section
            key={r.slug}
            className={`glass-card tada-card${r.pinned ? " tada-card--pinned" : ""}${r.dismissed ? " tada-card--dismissed" : ""}${rerunning.has(r.slug) ? " tada-card--rerunning" : ""}${isRunning ? " tada-card--running" : ""}${cardUnread ? " tada-card--unread" : ""}`}
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
                {r.title}
                {cardUnread && <span className="tada-unread-dot" />}
                {r.dismissed && <span className="tada-dismissed-badge">Dismissed</span>}
                {rerunFailed.has(r.slug) && <span className="tada-rerun-failed-badge">Rerun failed</span>}
              </h3>
              <div className="tada-card-actions" onClick={(e) => e.stopPropagation()}>
                <button
                  className={`tada-card-action-btn${rerunning.has(r.slug) ? " rerunning" : ""}`}
                  title={rerunning.has(r.slug) ? "Rerunning\u2026" : "Re-run"}
                  onClick={() => rerun(r.slug)}
                  disabled={rerunning.has(r.slug)}
                >
                  <svg width="12" height="12" viewBox="0 0 16 16" fill="none">
                    <path d="M2 8a6 6 0 0110.47-4M14 8a6 6 0 01-10.47 4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
                    <path d="M12 1v3.5h-3.5M4 15v-3.5h3.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </button>
                <button
                  className="tada-card-action-btn"
                  title="Give feedback"
                  onClick={() => handleCardClick(r.slug, true)}
                >
                  <svg width="12" height="12" viewBox="0 0 16 16" fill="none">
                    <path d="M2 3h12v8H5l-3 3V3z" stroke="currentColor" fill="none" strokeWidth="1.3" strokeLinejoin="round"/>
                  </svg>
                </button>
                <button
                  className={`tada-card-action-btn tada-thumbs-up${r.thumbs === "up" ? " active" : ""}`}
                  title="Thumbs up"
                  onClick={() => thumbs(r.slug, "up")}
                >
                  <svg width="12" height="12" viewBox="0 0 16 16" fill="none">
                    <path d="M5 14V7m0 7H3.5A1.5 1.5 0 012 12.5v-4A1.5 1.5 0 013.5 7H5m0 7h5.59a2 2 0 001.96-1.61l.86-4.28A1.5 1.5 0 0011.93 6H9V3.5A1.5 1.5 0 007.5 2L5 7"
                      stroke="currentColor" fill={r.thumbs === "up" ? "currentColor" : "none"} strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </button>
                <button
                  className={`tada-card-action-btn tada-thumbs-down${r.thumbs === "down" ? " active" : ""}`}
                  title="Thumbs down"
                  onClick={() => thumbs(r.slug, "down")}
                >
                  <svg width="12" height="12" viewBox="0 0 16 16" fill="none">
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
                    <svg width="12" height="12" viewBox="0 0 14 14" fill="none">
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
                      <svg width="12" height="12" viewBox="0 0 14 14" fill="none">
                        <path d="M7.5 1.5L10.5 4.5L9 8L10.5 12.5L7 9L3.5 12.5L5 8L3.5 4.5L6.5 1.5L7.5 1.5Z"
                          stroke="currentColor" fill={r.pinned ? "currentColor" : "none"} strokeWidth="1" strokeLinejoin="round"/>
                      </svg>
                    </button>
                    <button
                      className="tada-card-action-btn"
                      title="Dismiss"
                      onClick={() => dismiss(r.slug)}
                    >
                      <svg width="12" height="12" viewBox="0 0 14 14" fill="none">
                        <path d="M3 3l8 8M11 3l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                      </svg>
                    </button>
                  </>
                )}
              </div>
            </div>
            <div className="tada-card-schedule tada-card-schedule--clickable" onClick={(e) => openScheduleEditor(e, r)}>
              <span className="tada-card-frequency">{effectiveFrequency(r)}</span>
              {effectiveFrequency(r) !== "once" && (
                <span className="tada-card-time">
                  <svg width="11" height="11" viewBox="0 0 14 14" fill="none" style={{ marginRight: 3, verticalAlign: -1 }}>
                    <circle cx="7" cy="7" r="5.5" stroke="currentColor" strokeWidth="1.2"/>
                    <path d="M7 4.5V7l2.5 1.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                  {displayTime(r)}
                </span>
              )}
              <span className="tada-card-date">{timeAgo(r.completed_at)}</span>
            </div>
            <p className="tada-card-desc">{r.description}</p>

            {editingSlug === r.slug && (
              <div className="tada-schedule-editor" onClick={(e) => e.stopPropagation()}>
                <div className="tada-schedule-editor-row">
                  <div className="tada-schedule-field">
                    <span>Frequency</span>
                    <TadaDropdown value={editFreq} options={FREQUENCY_OPTIONS} onChange={setEditFreq} />
                  </div>
                  {editFreq === "weekly" && (
                    <div className="tada-schedule-field">
                      <span>Day</span>
                      <TadaDropdown value={editDay} options={DAYS} onChange={setEditDay} />
                    </div>
                  )}
                  {editFreq !== "once" && (
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

            {isRunning && (
              <div className="tada-card-running">
                <div className="tada-card-running-row">
                  <div className="feature-activity-spinner" />
                  <span className="tada-card-running-text">Running…</span>
                  {runPct > 0 && <span className="tada-card-running-pct">{Math.round(runPct)}%</span>}
                </div>
                {runPct > 0 && (
                  <div className="feature-activity-progress-track">
                    <div className="feature-activity-progress-fill" style={{ width: `${runPct}%` }} />
                  </div>
                )}
              </div>
            )}
          </section>
          );
        })
      )}
      <div style={{ minHeight: 24, flexShrink: 0 }} />
    </div>
  );
}
