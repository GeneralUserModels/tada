import { useEffect, useState } from "react";

interface Props {
  connectorName: string;
  onClose: () => void;
  onGranted?: () => void;
}

export function PermissionModal({ connectorName, onClose, onGranted }: Props) {
  const [info, setInfo] = useState<ConnectorPermissionInfo | null>(null);
  const [statusText, setStatusText] = useState("Waiting for access\u2026");
  const [granted, setGranted] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function init() {
      const permInfo = await window.powernap.getConnectorPermissionInfo(connectorName);
      if (cancelled || !permInfo) return;
      setInfo(permInfo);

      if (permInfo.hasRequest) {
        const ok = await window.powernap.requestConnectorPermission(connectorName);
        if (cancelled) return;
        if (ok) {
          handleGranted();
          return;
        }
      }
    }

    init();
    return () => { cancelled = true; };
  }, [connectorName]);

  // Poll for permission after modal opens
  useEffect(() => {
    if (granted) return;

    const id = setInterval(async () => {
      const ok = await window.powernap.checkConnectorPermission(connectorName);
      if (ok) {
        clearInterval(id);
        handleGranted();
      }
    }, 1500);

    return () => clearInterval(id);
  }, [connectorName, granted]);

  async function handleGranted() {
    setGranted(true);
    setStatusText("Access granted!");
    await window.powernap.updateConnector(connectorName, true);
    setTimeout(() => {
      onClose();
      onGranted?.();
    }, 800);
  }

  if (!info) return null;

  return (
    <div style={{
      display: "flex",
      position: "fixed",
      inset: 0,
      background: "rgba(44,58,40,0.35)",
      backdropFilter: "blur(6px)",
      WebkitBackdropFilter: "blur(6px)",
      zIndex: 2000,
      alignItems: "center",
      justifyContent: "center",
    }}>
      <div style={{
        background: "#F4F2EE",
        borderRadius: 16,
        padding: "28px 28px 22px",
        maxWidth: 340,
        width: "calc(100% - 48px)",
        boxShadow: "0 12px 48px rgba(44,58,40,0.18)",
        border: "1px solid rgba(132,177,121,0.15)",
      }}>
        <div style={{
          width: 38, height: 38, borderRadius: 10,
          background: "rgba(199,234,187,0.35)", color: "#84B179",
          display: "flex", alignItems: "center", justifyContent: "center",
          marginBottom: 14,
        }}>
          <svg width="18" height="18" viewBox="0 0 16 16" fill="none">
            <path d="M8 2a3 3 0 00-3 3v2H4a1 1 0 00-1 1v5a1 1 0 001 1h8a1 1 0 001-1V8a1 1 0 00-1-1h-1V5a3 3 0 00-3-3zm0 1.5A1.5 1.5 0 019.5 5v2h-3V5A1.5 1.5 0 018 3.5z" fill="currentColor"/>
          </svg>
        </div>
        <div style={{ fontSize: 15, fontWeight: 700, letterSpacing: "-0.01em", color: "#2C3A28", marginBottom: 6 }}>
          {info.title}
        </div>
        <p style={{ fontSize: 12, color: "#6B7A65", lineHeight: 1.6, marginBottom: 14 }}>
          {info.body}
        </p>
        <ol style={{ fontSize: 11.5, color: "#2C3A28", lineHeight: 1.8, paddingLeft: 18, marginBottom: 16 }}>
          {info.steps.map((s, i) => <li key={i}>{s}</li>)}
        </ol>
        <div style={{ fontSize: 11, color: "#9BA896", marginBottom: 18, display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{
            display: "inline-block", width: 7, height: 7, borderRadius: "50%",
            background: granted ? "#84B179" : "#A2CB8B",
            animation: "perm-pulse 1.2s ease-in-out infinite",
          }}></span>
          <span>{statusText}</span>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button
            style={{
              flex: 1, padding: "8px 0", borderRadius: 20,
              border: "1px solid rgba(132,177,121,0.25)",
              background: "rgba(199,234,187,0.2)", fontSize: 11.5,
              fontWeight: 600, color: "#84B179", cursor: "pointer", fontFamily: "inherit",
            }}
            onClick={() => window.powernap.openFdaSettings(connectorName)}
          >
            Open Settings
          </button>
          <button
            style={{
              padding: "8px 16px", borderRadius: 20, border: "1px solid transparent",
              background: "transparent", fontSize: 11.5, color: "#9BA896",
              cursor: "pointer", fontFamily: "inherit",
            }}
            onClick={onClose}
          >
            Skip
          </button>
        </div>
      </div>
      <style>{`
        @keyframes perm-pulse {
          0%, 100% { opacity: 0.3; transform: scale(0.85); }
          50% { opacity: 1; transform: scale(1.1); }
        }
      `}</style>
    </div>
  );
}
