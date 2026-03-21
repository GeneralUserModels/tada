import { ActiveView } from "../context/AppContext";

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

export function Sidebar({ activeView, connected, onNavigate }: Props) {
  return (
    <nav id="sidebar">
      <div className="sidebar-brand">
        <div className="brand-icon">
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <text x="1" y="17" fontFamily="sans-serif" fontWeight="bold" fontSize="11" fill="url(#brandGrad)">Z</text>
            <text x="7" y="13" fontFamily="sans-serif" fontWeight="bold" fontSize="8" fill="url(#brandGrad)" opacity="0.75">z</text>
            <text x="12" y="9" fontFamily="sans-serif" fontWeight="bold" fontSize="6" fill="url(#brandGrad)" opacity="0.5">z</text>
            <defs>
              <linearGradient id="brandGrad" x1="2" y1="2" x2="18" y2="18">
                <stop stopColor="#84B179"/>
                <stop offset="1" stopColor="#A2CB8B"/>
              </linearGradient>
            </defs>
          </svg>
        </div>
        <span className="brand-name">powerNAP</span>
        <div id="connection-status" className={`conn-badge ${connected ? "connected" : "disconnected"}`}>
          <span className="conn-dot"></span>
        </div>
      </div>

      <div className="sidebar-nav">
        {navItems.map(({ view, label, icon }) => (
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
