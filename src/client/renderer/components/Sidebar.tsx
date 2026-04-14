import React from "react";
import { ActiveView } from "../context/AppContext";
import { useFeatureFlags, getFlag } from "../featureFlags";

interface Props {
  activeView: ActiveView;
  connected: boolean;
  seekerHasQuestions: boolean;
  onNavigate: (view: ActiveView) => void;
}

const navItems: { view: ActiveView; label: string; icon: JSX.Element }[] = [
  {
    view: "connectors",
    label: "Connectors",
    icon: (
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <path d="M6 2v3H3v6h3v3h4v-3h3V5h-3V2H6z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round"/>
      </svg>
    ),
  },
  {
    view: "tada",
    label: "Tada",
    icon: (
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <path d="M8 1l1.8 3.6L14 5.3l-3 2.9.7 4.1L8 10.5 4.3 12.3l.7-4.1-3-2.9 4.2-.7L8 1z"
          stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round"/>
      </svg>
    ),
  },
  {
    view: "pensieve",
    label: "Pensieve",
    icon: (
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <path d="M8 2C5.2 2 3 4.2 3 7c0 1.5.7 2.9 1.7 3.8.3.3.5.7.5 1.2v.5c0 .8.7 1.5 1.5 1.5h2.6c.8 0 1.5-.7 1.5-1.5V12c0-.5.2-.9.5-1.2C12.3 9.9 13 8.5 13 7c0-2.8-2.2-5-5-5z"
          stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round"/>
        <path d="M6 14.5h4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
      </svg>
    ),
  },
  {
    view: "seeker",
    label: "Seeker",
    icon: (
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <circle cx="7" cy="7" r="4.5" stroke="currentColor" strokeWidth="1.3"/>
        <path d="M10.5 10.5L14 14" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
      </svg>
    ),
  },
  {
    view: "usermodel",
    label: "User Model",
    icon: (
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <circle cx="8" cy="5.5" r="2.5" stroke="currentColor" strokeWidth="1.3"/>
        <path d="M3 14c0-2.8 2.2-5 5-5s5 2.2 5 5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
      </svg>
    ),
  },
  {
    view: "settings",
    label: "Settings",
    icon: (
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <circle cx="8" cy="8" r="2.5" stroke="currentColor" strokeWidth="1.3"/>
        <path d="M8 1v2M8 13v2M1 8h2M13 8h2M3.05 3.05l1.41 1.41M11.54 11.54l1.41 1.41M3.05 12.95l1.41-1.41M11.54 4.46l1.41-1.41" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
      </svg>
    ),
  },
];

const FLAG_FOR_VIEW: Partial<Record<ActiveView, string>> = {
  tada: "moments",
  pensieve: "memory",
  seeker: "seeker",
};

export function Sidebar({ activeView, connected, seekerHasQuestions, onNavigate }: Props) {
  const featureFlags = useFeatureFlags();

  const visibleItems = navItems.filter(({ view }) => {
    const flag = FLAG_FOR_VIEW[view];
    if (flag && !getFlag(featureFlags, flag)) return false;
    return true;
  });

  return (
    <nav id="sidebar">
      <div className="sidebar-brand">
        <div className="brand-icon">🎉</div>
        <span className="brand-name">Tada</span>
        <div id="connection-status" className={`conn-badge ${connected ? "connected" : "disconnected"}`}>
          <span className="conn-dot"></span>
        </div>
      </div>

      <div className="sidebar-nav">
        {visibleItems.map(({ view, label, icon }) => (
          <button
            key={view}
            className={`nav-item${activeView === view ? " active" : ""}`}
            onClick={() => onNavigate(view)}
          >
            {icon}
            {label}
            {view === "seeker" && seekerHasQuestions && <span className="nav-notify-dot" />}
          </button>
        ))}
      </div>
    </nav>
  );
}
