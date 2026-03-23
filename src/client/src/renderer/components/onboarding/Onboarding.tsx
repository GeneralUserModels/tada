import { useEffect, useRef, useState } from "react";
import { AdvancedLLMSection } from "../shared/AdvancedLLMSection";

// ── Permission modal ──────────────────────────────────────────

function PermModal({
  connectorName,
  onClose,
  onGranted,
}: {
  connectorName: string;
  onClose: () => void;
  onGranted: () => void;
}) {
  const [info, setInfo] = useState<ConnectorPermissionInfo | null>(null);
  const [statusText, setStatusText] = useState("Waiting for access\u2026");
  const [grantedState, setGrantedState] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function init() {
      const permInfo = await window.powernap.getConnectorPermissionInfo(connectorName);
      if (cancelled || !permInfo) return;
      setInfo(permInfo);
      if (permInfo.hasRequest) {
        const ok = await window.powernap.requestConnectorPermission(connectorName);
        if (!cancelled && ok) { handleGranted(); }
      }
    }
    init();
    return () => { cancelled = true; };
  }, [connectorName]);

  useEffect(() => {
    if (grantedState) return;
    const id = setInterval(async () => {
      const ok = await window.powernap.checkConnectorPermission(connectorName);
      if (ok) { clearInterval(id); handleGranted(); }
    }, 1500);
    return () => clearInterval(id);
  }, [connectorName, grantedState]);

  function handleGranted() {
    setGrantedState(true);
    setStatusText("Access granted!");
    setTimeout(() => { onClose(); onGranted(); }, 700);
  }

  if (!info) return null;

  return (
    <div id="perm-modal-overlay" style={{
      display: "flex", position: "fixed", inset: 0,
      background: "rgba(44,58,40,0.35)", backdropFilter: "blur(6px)",
      WebkitBackdropFilter: "blur(6px)", zIndex: 2000,
      alignItems: "center", justifyContent: "center", WebkitAppRegion: "no-drag",
    }}>
      <div style={{
        background: "#F4F2EE", borderRadius: 16, padding: "28px 28px 22px",
        maxWidth: 320, width: "calc(100% - 48px)",
        boxShadow: "0 12px 48px rgba(44,58,40,0.18)",
        border: "1px solid rgba(132,177,121,0.15)",
      }}>
        <div style={{
          width: 38, height: 38, borderRadius: 10,
          background: "rgba(199,234,187,0.35)", color: "#84B179",
          display: "flex", alignItems: "center", justifyContent: "center", marginBottom: 14,
        }}>
          <svg width="18" height="18" viewBox="0 0 16 16" fill="none">
            <path d="M8 2a3 3 0 00-3 3v2H4a1 1 0 00-1 1v5a1 1 0 001 1h8a1 1 0 001-1V8a1 1 0 00-1-1h-1V5a3 3 0 00-3-3zm0 1.5A1.5 1.5 0 019.5 5v2h-3V5A1.5 1.5 0 018 3.5z" fill="currentColor"/>
          </svg>
        </div>
        <div id="perm-modal-title" style={{ fontSize: 15, fontWeight: 700, letterSpacing: "-0.01em", color: "var(--text)", marginBottom: 6 }}>{info.title}</div>
        <p id="perm-modal-body" style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.6, marginBottom: 14 }}>{info.body}</p>
        <ol id="perm-modal-steps" style={{ fontSize: 11.5, color: "var(--text)", lineHeight: 1.8, paddingLeft: 18, marginBottom: 16 }}>
          {info.steps.map((s, i) => <li key={i}>{s}</li>)}
        </ol>
        <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginBottom: 18, display: "flex", alignItems: "center", gap: 6 }}>
          <span id="perm-modal-spinner" style={{
            display: "inline-block", width: 7, height: 7, borderRadius: "50%",
            background: grantedState ? "#84B179" : "#A2CB8B",
            animation: "perm-pulse 1.2s ease-in-out infinite",
          }}></span>
          <span>{statusText}</span>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn btn-outline btn-sm" style={{ flex: 1 }}
            onClick={() => window.powernap.openFdaSettings(connectorName)}>Open Settings</button>
          <button className="btn btn-ghost btn-sm" onClick={onClose}>Skip</button>
        </div>
      </div>
    </div>
  );
}

// ── Step indicator ────────────────────────────────────────────

function StepIndicator({ current, total }: { current: number; total: number }) {
  const items: JSX.Element[] = [];
  for (let i = 0; i < total; i++) {
    if (i > 0) items.push(<div key={`line-${i}`} className="step-line"></div>);
    items.push(
      <div
        key={`dot-${i}`}
        className={`step-dot${i === current ? " active" : i < current ? " done" : ""}`}
      ></div>
    );
  }
  return <div className="steps">{items}</div>;
}

// ── Main Onboarding component ─────────────────────────────────

export function Onboarding() {
  const [step, setStep] = useState(0);
  const [permModal, setPermModal] = useState<{ name: string; onGranted: () => void } | null>(null);

  // Google login state
  const [googleUser, setGoogleUser] = useState<{ name: string; email: string } | null>(null);
  const [googleLoading, setGoogleLoading] = useState(false);
  const [googleError, setGoogleError] = useState("");

  // Connector state
  const [screenGranted, setScreenGranted] = useState(false);
  const [calendarConnected, setCalendarConnected] = useState(false);
  const [gmailConnected, setGmailConnected] = useState(false);
  const [outlookConnected, setOutlookConnected] = useState(false);
  const [notifAvailable, setNotifAvailable] = useState(false);
  const [fsAvailable, setFsAvailable] = useState(false);
  const [notifEnabled, setNotifEnabled] = useState(false);
  const [fsEnabled, setFsEnabled] = useState(false);
  const [connectingGoogle, setConnectingGoogle] = useState<string | null>(null);
  const [connectingOutlook, setConnectingOutlook] = useState(false);

  // Model + API key state
  const [model, setModel] = useState("gemini/gemini-3-flash-preview");
  const [geminiKey, setGeminiKey] = useState("");
  const [tinkerKey, setTinkerKey] = useState("");
  const [wandbKey, setWandbKey] = useState("");
  const [tinkerError, setTinkerError] = useState("");
  const [advancedValues, setAdvancedValues] = useState<Record<string, string>>({});

  // Check screen permission when entering step 2
  useEffect(() => {
    if (step !== 2) return;
    async function checkScreen() {
      const granted = await window.powernap.checkConnectorPermission("screen");
      setScreenGranted(granted);
      if (!granted) {
        setPermModal({ name: "screen", onGranted: () => setScreenGranted(true) });
      }
    }
    checkScreen();

    async function checkAvailability() {
      const notif = await window.powernap.checkNotifications();
      setNotifAvailable(notif);
      if (notif) setNotifEnabled(true);
      const fs = await window.powernap.checkFilesystem();
      setFsAvailable(fs);
      if (fs) setFsEnabled(true);
    }
    checkAvailability();
  }, [step]);

  const handleGoogleLogin = async () => {
    setGoogleLoading(true);
    setGoogleError("");
    try {
      const result = await window.powernap.googleLogin();
      setGoogleUser(result);
    } catch {
      setGoogleError("Sign in failed. Please try again.");
    } finally {
      setGoogleLoading(false);
    }
  };

  const handleConnectGoogle = async (svc: string) => {
    setConnectingGoogle(svc);
    try {
      const scope = svc === "calendar" ? (gmailConnected ? "calendar,gmail" : "calendar")
                                       : (calendarConnected ? "calendar,gmail" : "gmail");
      const ok = await window.powernap.connectGoogle(scope);
      if (ok) {
        if (svc === "calendar") setCalendarConnected(true);
        else setGmailConnected(true);
      }
    } finally {
      setConnectingGoogle(null);
    }
  };

  const handleConnectOutlook = async () => {
    setConnectingOutlook(true);
    try {
      const ok = await window.powernap.connectOutlook();
      if (ok) setOutlookConnected(true);
    } finally {
      setConnectingOutlook(false);
    }
  };

  const validateTinker = (val: string) => {
    if (val && !val.startsWith("tml-")) {
      setTinkerError('Tinker keys must start with "tml-"');
      return false;
    }
    setTinkerError("");
    return true;
  };

  const handleSubmit = () => {
    const advanced: Record<string, string> = {};
    for (const [k, v] of Object.entries(advancedValues)) {
      if (v.trim()) advanced[k] = v.trim();
    }
    window.powernap.submitOnboarding({
      reward_llm: model.trim() || "gemini/gemini-3-flash-preview",
      default_llm_api_key: geminiKey.trim(),
      ...advanced,
      tinker_api_key: tinkerKey.trim() || undefined,
      wandb_api_key: wandbKey.trim() || undefined,
      user_name: googleUser?.name,
      user_email: googleUser?.email,
      connectors: {
        screen: screenGranted,
        calendar: calendarConnected,
        gmail: gmailConnected,
        outlook_calendar: outlookConnected,
        outlook_email: outlookConnected,
        notifications: notifEnabled,
        filesystem: fsEnabled,
      },
      google_configured: { calendar: !!googleUser, gmail: !!googleUser },
      outlook_configured: { calendar: outlookConnected, email: outlookConnected },
    });
  };

  return (
    <div className="wrapper">
      {permModal && (
        <PermModal
          connectorName={permModal.name}
          onClose={() => setPermModal(null)}
          onGranted={permModal.onGranted}
        />
      )}

      <StepIndicator current={step} total={4} />

      {/* Page 0: Welcome */}
      {step === 0 && (
        <div className="page active">
          <div className="welcome-brand">
            <svg width="28" height="28" viewBox="0 0 20 20" fill="none">
              <text x="1" y="17" fontFamily="sans-serif" fontWeight="bold" fontSize="11" fill="url(#bGrad)">Z</text>
              <text x="7" y="13" fontFamily="sans-serif" fontWeight="bold" fontSize="8" fill="url(#bGrad)" opacity="0.75">z</text>
              <text x="12" y="9" fontFamily="sans-serif" fontWeight="bold" fontSize="6" fill="url(#bGrad)" opacity="0.5">z</text>
              <defs>
                <linearGradient id="bGrad" x1="2" y1="2" x2="18" y2="18">
                  <stop stopColor="#84B179"/><stop offset="1" stopColor="#A2CB8B"/>
                </linearGradient>
              </defs>
            </svg>
            <span>powerNAP</span>
          </div>
          <p className="welcome-subtitle">A few quick steps to get you up and running. This only takes a minute.</p>
          <div className="glass-card">
            <div className="welcome-features">
              <div className="welcome-feature">
                <div className="wf-icon">
                  <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><rect x="2" y="3" width="12" height="10" rx="2" stroke="currentColor" strokeWidth="1.3"/><circle cx="8" cy="8" r="2" fill="currentColor"/></svg>
                </div>
                <span>Grant screen recording permission so PowerNap can observe your workflow</span>
              </div>
              <div className="welcome-feature">
                <div className="wf-icon">
                  <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M8 2v4l3 2" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/><path d="M2.5 8.5A5.5 5.5 0 1013.5 8" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/></svg>
                </div>
                <span>Choose your prediction model</span>
              </div>
              <div className="welcome-feature">
                <div className="wf-icon">
                  <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M4 12V7M8 12V4M12 12V9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
                </div>
                <span>Connect your API keys</span>
              </div>
            </div>
          </div>
          <div className="btn-row">
            <div></div>
            <button className="btn btn-primary" onClick={() => setStep(1)}>Get Started</button>
          </div>
        </div>
      )}

      {/* Page 1: Google Login */}
      {step === 1 && (
        <div className="page active">
          <div className="page-icon">
            <svg width="22" height="22" viewBox="0 0 16 16" fill="none"><path d="M8 1a7 7 0 1 0 0 14A7 7 0 0 0 8 1Zm0 2.5a2 2 0 1 1 0 4 2 2 0 0 1 0-4ZM8 13c-1.7 0-3.2-.9-4-2.2.02-1.3 2.7-2 4-2s3.98.7 4 2c-.8 1.3-2.3 2.2-4 2.2Z" fill="currentColor"/></svg>
          </div>
          <div className="page-title">Sign In</div>
          <p className="page-desc">Sign in with your Google account so we know who you are.</p>
          <div className="glass-card" style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 16 }}>
            {!googleUser && (
              <button
                className="btn"
                style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 24px", background: "#fff", border: "1px solid #dadce0", borderRadius: 4, fontSize: 14, fontWeight: 500, color: "#3c4043" }}
                onClick={handleGoogleLogin}
                disabled={googleLoading}
              >
                <svg width="18" height="18" viewBox="0 0 18 18"><path d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844a4.14 4.14 0 0 1-1.796 2.716v2.259h2.908c1.702-1.567 2.684-3.875 2.684-6.615Z" fill="#4285F4"/><path d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.26c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18Z" fill="#34A853"/><path d="M3.964 10.71A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.997 8.997 0 0 0 0 9c0 1.452.348 2.827.957 4.042l3.007-2.332Z" fill="#FBBC05"/><path d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.958L3.964 6.29C4.672 4.163 6.656 2.58 9 2.58Z" fill="#EA4335"/></svg>
                {googleLoading ? "Signing in..." : "Sign in with Google"}
              </button>
            )}
            <div style={{ fontSize: 12.5, color: googleUser ? "var(--active-green)" : googleError ? "var(--danger)" : "var(--text-secondary)", textAlign: "center", minHeight: 20 }}>
              {googleUser
                ? <><strong>Signed in as {googleUser.name}</strong><br/>{googleUser.email}</>
                : googleError || ""}
            </div>
          </div>
          <div className="btn-row">
            <button className="btn btn-ghost" onClick={() => setStep(0)}>Back</button>
            <button className="btn btn-primary" disabled={!googleUser} onClick={() => setStep(2)}>Continue</button>
          </div>
        </div>
      )}

      {/* Page 2: Connectors */}
      {step === 2 && (
        <div className="page active">
          <div className="page-icon">
            <svg width="22" height="22" viewBox="0 0 16 16" fill="none"><path d="M6 2v3H3v6h3v3h4v-3h3V5h-3V2H6z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round"/></svg>
          </div>
          <div className="page-title">Connectors</div>
          <p className="page-desc">Choose which data sources PowerNap can access to learn your patterns.</p>
          <div className="glass-card" style={{ padding: 16 }}>
            <div className="connector-list">
              {/* Screen Recording */}
              <div className="connector-row">
                <div className="connector-icon">
                  <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><rect x="2" y="3" width="12" height="10" rx="2" stroke="currentColor" strokeWidth="1.3"/><circle cx="8" cy="8" r="2" fill="currentColor"/></svg>
                </div>
                <div className="connector-info">
                  <div className="connector-name">Screen Recording <span className="required-tag">Required</span></div>
                  <div className="connector-desc">Captures your screen to observe workflow</div>
                </div>
                <div className="connector-action">
                  {screenGranted
                    ? <span className="perm-badge granted">Granted</span>
                    : <button className="btn btn-outline btn-sm" onClick={() => setPermModal({ name: "screen", onGranted: () => setScreenGranted(true) })}>Grant Access</button>
                  }
                </div>
              </div>

              {/* Google Calendar */}
              <div className="connector-row">
                <div className="connector-icon">
                  <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><rect x="2" y="3" width="12" height="11" rx="1.5" stroke="currentColor" strokeWidth="1.3"/><path d="M2 6.5h12" stroke="currentColor" strokeWidth="1.3"/><path d="M5 1.5v3M11 1.5v3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/></svg>
                </div>
                <div className="connector-info">
                  <div className="connector-name">Google Calendar</div>
                  <div className="connector-desc">Read your upcoming events for context</div>
                </div>
                <div className="connector-action">
                  {calendarConnected
                    ? <span className="connected-badge">Connected</span>
                    : <button className="btn btn-outline btn-sm" disabled={connectingGoogle === "calendar"} onClick={() => handleConnectGoogle("calendar")}>{connectingGoogle === "calendar" ? "Connecting..." : "Connect"}</button>
                  }
                </div>
              </div>

              {/* Gmail */}
              <div className="connector-row">
                <div className="connector-icon">
                  <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><rect x="1.5" y="3.5" width="13" height="9" rx="1.5" stroke="currentColor" strokeWidth="1.3"/><path d="M1.5 4.5L8 9l6.5-4.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/></svg>
                </div>
                <div className="connector-info">
                  <div className="connector-name">Gmail</div>
                  <div className="connector-desc">Read recent emails for context</div>
                </div>
                <div className="connector-action">
                  {gmailConnected
                    ? <span className="connected-badge">Connected</span>
                    : <button className="btn btn-outline btn-sm" disabled={connectingGoogle === "gmail"} onClick={() => handleConnectGoogle("gmail")}>{connectingGoogle === "gmail" ? "Connecting..." : "Connect"}</button>
                  }
                </div>
              </div>

              {/* Outlook (shared auth for calendar + email) */}
              <div className="connector-row">
                <div className="connector-icon">
                  <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><rect x="2" y="3" width="12" height="11" rx="1.5" stroke="currentColor" strokeWidth="1.3"/><path d="M2 6.5h12" stroke="currentColor" strokeWidth="1.3"/><path d="M5 1.5v3M11 1.5v3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/></svg>
                </div>
                <div className="connector-info">
                  <div className="connector-name">Outlook</div>
                  <div className="connector-desc">Calendar + Email (shared auth)</div>
                </div>
                <div className="connector-action">
                  {outlookConnected
                    ? <span className="connected-badge">Connected</span>
                    : <button className="btn btn-outline btn-sm" disabled={connectingOutlook} onClick={handleConnectOutlook}>{connectingOutlook ? "Connecting..." : "Connect"}</button>
                  }
                </div>
              </div>

              {/* Notifications */}
              <div className="connector-row">
                <div className="connector-icon">
                  <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M4 6a4 4 0 018 0v3l1.5 2H2.5L4 9V6z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round"/><path d="M6.5 13a1.5 1.5 0 003 0" stroke="currentColor" strokeWidth="1.3"/></svg>
                </div>
                <div className="connector-info">
                  <div className="connector-name">Notifications</div>
                  <div className="connector-desc">Read macOS notification history</div>
                </div>
                <div className="connector-action">
                  {notifAvailable
                    ? <label className="toggle"><input type="checkbox" checked={notifEnabled} onChange={(e) => setNotifEnabled(e.target.checked)}/><span className="toggle-slider"></span></label>
                    : <button className="btn btn-outline btn-sm" onClick={() => setPermModal({ name: "notifications", onGranted: () => { setNotifAvailable(true); setNotifEnabled(true); } })}>Grant Access</button>
                  }
                </div>
              </div>

              {/* Filesystem */}
              <div className="connector-row">
                <div className="connector-icon">
                  <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M2 4.5V13a1 1 0 001 1h10a1 1 0 001-1V6a1 1 0 00-1-1H7.5L6 3H3a1 1 0 00-1 1.5z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round"/></svg>
                </div>
                <div className="connector-info">
                  <div className="connector-name">Filesystem</div>
                  <div className="connector-desc">Watch Desktop, Documents, Downloads</div>
                </div>
                <div className="connector-action">
                  <label className="toggle">
                    <input type="checkbox" checked={fsEnabled} disabled={!fsAvailable} onChange={(e) => setFsEnabled(e.target.checked)}/>
                    <span className="toggle-slider"></span>
                  </label>
                </div>
              </div>
            </div>
          </div>
          <div className="btn-row">
            <button className="btn btn-ghost" onClick={() => setStep(1)}>Back</button>
            <button className="btn btn-primary" disabled={!screenGranted} onClick={() => setStep(3)}>Continue</button>
          </div>
        </div>
      )}

      {/* Page 3: Models & Keys */}
      {step === 3 && (
        <div className="page active">
          <div className="page-icon">
            <svg width="22" height="22" viewBox="0 0 16 16" fill="none"><path d="M4 12V7M8 12V4M12 12V9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
          </div>
          <div className="page-title">Models & Keys</div>
          <p className="page-desc">Configure your LLM provider. Uses LiteLLM format — any supported provider works.</p>
          <div className="glass-card">
            <div className="model-row">
              <span className="model-row-label">LLM <span className="required-tag">Required</span></span>
              <div className="model-row-fields">
                <div className="field">
                  <span>Model</span>
                  <input type="text" placeholder="gemini/gemini-3-flash-preview" value={model} onChange={(e) => setModel(e.target.value)}/>
                </div>
                <div className="field">
                  <span>API Key</span>
                  <input type="password" placeholder="AIza..." value={geminiKey} onChange={(e) => setGeminiKey(e.target.value)}/>
                </div>
              </div>
            </div>
            <AdvancedLLMSection values={advancedValues} setValues={setAdvancedValues} />
            <div className="model-row">
              <span className="model-row-label">Tinker <span className="optional-tag">optional</span></span>
              <div className="model-row-fields">
                <div className="field">
                  <span>API Key</span>
                  <input type="password" placeholder="tml-..." value={tinkerKey}
                    onChange={(e) => { setTinkerKey(e.target.value); validateTinker(e.target.value); }}/>
                  {tinkerError && <span className="field-hint" style={{ color: "var(--danger)" }}>{tinkerError}</span>}
                </div>
                <div className="field">
                  <span>W&amp;B API Key</span>
                  <input type="password" placeholder="wandb-..." value={wandbKey} onChange={(e) => setWandbKey(e.target.value)}/>
                </div>
              </div>
            </div>
          </div>
          <div className="btn-row">
            <button className="btn btn-ghost" onClick={() => setStep(2)}>Back</button>
            <button className="btn btn-primary" disabled={!model.trim() || !geminiKey.trim() || !!tinkerError} onClick={handleSubmit}>Finish Setup</button>
          </div>
        </div>
      )}
    </div>
  );
}
