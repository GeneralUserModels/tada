import React from "react";
import { ActiveView } from "../context/AppContext";
import { useFeatureFlags, getFlag } from "../featureFlags";

interface Props {
  activeView: ActiveView;
  connected: boolean;
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
    label: "Ta-Da",
    icon: (
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <path d="M8 1l1.8 3.6L14 5.3l-3 2.9.7 4.1L8 10.5 4.3 12.3l.7-4.1-3-2.9 4.2-.7L8 1z"
          stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round"/>
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
};

export function Sidebar({ activeView, connected, onNavigate }: Props) {
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
          </button>
        ))}
      </div>
    </nav>
  );
}
