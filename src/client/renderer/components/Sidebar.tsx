import React from "react";
import { ActiveView, AgentActivityInfo } from "../context/AppContext";
import { useFeatureFlags, getFlag } from "../featureFlags";

interface Props {
  activeView: ActiveView;
  connected: boolean;
  agentActivities: Record<string, AgentActivityInfo>;
  onNavigate: (view: ActiveView) => void;
}

const AGENTS_FOR_VIEW: Partial<Record<ActiveView, string[]>> = {
  tada: ["moments_discovery", "moment_run"],
  memex: ["memory"],
  seeker: ["seeker"],
  chat: ["chat"],
};

const navItems: { view: ActiveView; label: string; icon: JSX.Element }[] = [
  {
    view: "activity",
    label: "Activity",
    icon: (
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <path d="M3 3.5h10M3 8h10M3 12.5h7" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
      </svg>
    ),
  },
  {
    view: "chat",
    label: "Assistant",
    icon: (
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <path d="M2.5 4.5a2 2 0 0 1 2-2h7a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2H7l-3 2.5v-2.5h-.5a2 2 0 0 1-2-2v-5z"
          stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round"/>
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
    view: "memex",
    label: "Memex",
    icon: (
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <circle cx="8" cy="3.5" r="1.5" stroke="currentColor" strokeWidth="1.3"/>
        <circle cx="3.5" cy="8" r="1.5" stroke="currentColor" strokeWidth="1.3"/>
        <circle cx="12.5" cy="8" r="1.5" stroke="currentColor" strokeWidth="1.3"/>
        <circle cx="5.5" cy="13" r="1.5" stroke="currentColor" strokeWidth="1.3"/>
        <circle cx="10.5" cy="13" r="1.5" stroke="currentColor" strokeWidth="1.3"/>
        <path d="M6.5 4.5L5 6.5M9.5 4.5L11 6.5M3.5 9.5L5 11.5M12.5 9.5L11 11.5" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round"/>
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
  memex: "memory",
  seeker: "seeker",
  chat: "chat",
};

export function Sidebar({ activeView, connected, agentActivities, onNavigate }: Props) {
  const featureFlags = useFeatureFlags();

  const visibleItems = navItems.filter(({ view }) => {
    const flag = FLAG_FOR_VIEW[view];
    if (flag && !getFlag(featureFlags, flag)) return false;
    return true;
  });

  const isViewActive = (view: ActiveView) => {
    const agents = AGENTS_FOR_VIEW[view];
    return agents?.some((a) => agentActivities[a]) ?? false;
  };

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
            {isViewActive(view) && <span className="nav-activity-spinner" />}
          </button>
        ))}
      </div>
    </nav>
  );
}
