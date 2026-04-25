import React, { useEffect, useState } from "react";
import { SubPermissionRow } from "./SubPermissionRow";

const CONNECTOR_ICONS: Record<string, JSX.Element> = {
  monitor: (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
      <rect x="2" y="3" width="12" height="10" rx="2" stroke="currentColor" strokeWidth="1.3"/>
      <circle cx="8" cy="8" r="2" fill="currentColor"/>
    </svg>
  ),
  calendar: (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
      <rect x="2" y="3" width="12" height="11" rx="1.5" stroke="currentColor" strokeWidth="1.3"/>
      <path d="M2 6.5h12" stroke="currentColor" strokeWidth="1.3"/>
      <path d="M5 1.5v3M11 1.5v3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
    </svg>
  ),
  mail: (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
      <rect x="1.5" y="3.5" width="13" height="9" rx="1.5" stroke="currentColor" strokeWidth="1.3"/>
      <path d="M1.5 4.5L8 9l6.5-4.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  ),
  bell: (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
      <path d="M4 6a4 4 0 018 0v3l1.5 2H2.5L4 9V6z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round"/>
      <path d="M6.5 13a1.5 1.5 0 003 0" stroke="currentColor" strokeWidth="1.3"/>
    </svg>
  ),
  folder: (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
      <path d="M2 4.5V13a1 1 0 001 1h10a1 1 0 001-1V6a1 1 0 00-1-1H7.5L6 3H3a1 1 0 00-1 1.5z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round"/>
    </svg>
  ),
  plug: (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
      <path d="M8 10v3M6 13h4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
      <rect x="4" y="6" width="8" height="4" rx="1" stroke="currentColor" strokeWidth="1.3"/>
      <path d="M6 6V3M10 6V3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
    </svg>
  ),
  microphone: (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
      <rect x="6" y="1" width="4" height="8" rx="2" stroke="currentColor" strokeWidth="1.3"/>
      <path d="M4 7a4 4 0 008 0" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
      <path d="M8 11v3M6 14h4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
    </svg>
  ),
  speaker: (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
      <path d="M2 5.5h2.5L8 2v12l-3.5-3.5H2a1 1 0 01-1-1v-3a1 1 0 011-1z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round"/>
      <path d="M11 5.5a3.5 3.5 0 010 5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
      <path d="M13 3.5a6.5 6.5 0 010 9" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
    </svg>
  ),
};

export interface ConnectorMeta {
  label: string;
  desc: string;
  icon: string;
  /**
   * Optional list of OS-level sub-permissions to surface as indented rows
   * beneath the parent connector. Used by `filesystem` to expose the
   * separate Desktop/Documents/Downloads TCC grants without duplicating
   * the connector itself.
   */
  subPermissions?: { key: string; label: string; desc?: string }[];
}

export const FILESYSTEM_SUB_PERMISSIONS = [
  { key: "folder_desktop",   label: "Desktop folder",   desc: "Watch for new files on your Desktop" },
  { key: "folder_documents", label: "Documents folder", desc: "Watch for new files in Documents" },
  { key: "folder_downloads", label: "Downloads folder", desc: "Watch for new files in Downloads" },
];

export const CONNECTOR_META: Record<string, ConnectorMeta> = {
  screen:           { label: "Screen Recording",  desc: "Captures your screen to observe workflow",       icon: "monitor" },
  calendar:         { label: "Google Calendar",    desc: "Read your upcoming events for context",          icon: "calendar" },
  gmail:            { label: "Gmail",              desc: "Read recent emails for context",                 icon: "mail" },
  outlook_calendar: { label: "Outlook Calendar",   desc: "Read your upcoming Outlook events for context",  icon: "calendar" },
  outlook_email:    { label: "Outlook Email",      desc: "Read recent Outlook emails for context",         icon: "mail" },
  notifications:    { label: "Notifications",      desc: "Read macOS notification history",                icon: "bell" },
  filesystem:       {
    label: "Filesystem",
    desc: "Watch Desktop, Documents, Downloads",
    icon: "folder",
    subPermissions: FILESYSTEM_SUB_PERMISSIONS,
  },
  microphone:       { label: "Microphone",         desc: "Transcribe speech from your microphone",         icon: "microphone" },
  system_audio:     { label: "System Audio",       desc: "Transcribe system audio output",                 icon: "speaker" },
};

interface Props {
  name: string;
  info: ConnectorInfo;
  calendarOn: boolean;
  gmailOn: boolean;
  toggling: boolean;
  onToggle: (name: string, enabled: boolean) => Promise<void>;
  onConnectGoogle: (svc: string, otherIsOn: boolean) => Promise<void>;
  onConnectOutlook: () => Promise<void>;
  onRetry: (name: string) => Promise<void>;
}

export function ConnectorItem({
  name, info, calendarOn, gmailOn, toggling,
  onToggle, onConnectGoogle, onConnectOutlook, onRetry,
}: Props) {
  const meta = CONNECTOR_META[name] ?? { label: name, desc: "", icon: "plug" };
  const icon = CONNECTOR_ICONS[meta.icon];
  const [waitingPermission, setWaitingPermission] = useState(false);
  const [permissionGranted, setPermissionGranted] = useState<boolean | null>(null);

  // Audio connectors: check OS permission on mount
  const isAudioConnector = name === "microphone" || name === "system_audio";
  useEffect(() => {
    if (!isAudioConnector) return;
    window.tada.checkConnectorPermission(name).then(setPermissionGranted);
  }, [name, isAudioConnector]);

  // Clear waiting state when error resolves
  useEffect(() => {
    if (!info.error) setWaitingPermission(false);
  }, [info.error]);

  // Poll for OS permission grant on screen/notifications/audio
  useEffect(() => {
    if (!waitingPermission) return;

    const id = setInterval(async () => {
      const ok = await window.tada.checkConnectorPermission(name);
      if (ok) {
        clearInterval(id);
        setWaitingPermission(false);
        setPermissionGranted(true);
        if (!isAudioConnector) await onRetry(name);
      }
    }, 1500);

    return () => clearInterval(id);
  }, [waitingPermission, name, onRetry, isAudioConnector]);

  async function handlePermissionClick() {
    setWaitingPermission(true);
    if (name === "screen") {
      await window.tada.requestConnectorPermission("screen");
    } else if (name === "microphone") {
      await window.tada.requestConnectorPermission("microphone");
    } else if (name === "system_audio") {
      await window.tada.requestConnectorPermission("system_audio");
    } else {
      window.tada.openFdaSettings(name);
    }
  }

  let action: JSX.Element;

  if (isAudioConnector && permissionGranted === false) {
    // Audio connectors: show "Grant Access" before showing toggle
    action = (
      <button
        className="pill-btn"
        style={{ fontSize: 10, padding: "3px 10px" }}
        disabled={waitingPermission}
        onClick={handlePermissionClick}
      >{waitingPermission ? "Waiting\u2026" : "Grant Access"}</button>
    );
  } else if (info.error) {
    let label: string;
    let handleClick: () => void;

    if (name === "calendar" || name === "gmail") {
      label = "Sign in";
      handleClick = () => onConnectGoogle(name, name === "calendar" ? gmailOn : calendarOn);
    } else if (name.startsWith("outlook_")) {
      label = "Sign in";
      handleClick = onConnectOutlook;
    } else if (name === "screen") {
      label = waitingPermission ? "Waiting\u2026" : "Grant Access";
      handleClick = handlePermissionClick;
    } else if (name === "notifications") {
      label = waitingPermission ? "Waiting\u2026" : "Open Settings";
      handleClick = handlePermissionClick;
    } else if (name === "microphone" || name === "system_audio") {
      label = waitingPermission ? "Waiting\u2026" : "Grant Access";
      handleClick = handlePermissionClick;
    } else {
      label = "Retry";
      handleClick = () => onRetry(name);
    }

    action = (
      <button
        className="pill-btn"
        style={{ fontSize: 10, padding: "3px 10px" }}
        disabled={waitingPermission}
        onClick={handleClick}
      >{label}</button>
    );
  } else if (!info.available && name.startsWith("outlook_")) {
    action = (
      <button
        className="pill-btn pill-start"
        style={{ fontSize: 10, padding: "3px 10px" }}
        onClick={onConnectOutlook}
      >Connect</button>
    );
  } else if (!info.available) {
    action = (
      <button
        className="pill-btn pill-start"
        style={{ fontSize: 10, padding: "3px 10px" }}
        onClick={() => onConnectGoogle(name, name === "calendar" ? gmailOn : calendarOn)}
      >Connect</button>
    );
  } else if (toggling) {
    action = (
      <span style={{
        width: 36, height: 20,
        display: "flex", alignItems: "center", justifyContent: "center",
      }}>
        <span style={{
          width: 14, height: 14, borderRadius: "50%",
          border: "2px solid rgba(132,177,121,0.3)",
          borderTopColor: "#84B179",
          animation: "spin 0.6s linear infinite",
          display: "inline-block",
        }} />
      </span>
    );
  } else {
    const bg = info.enabled ? "#84B179" : "rgba(132,177,121,0.15)";
    const knobX = info.enabled ? "translateX(16px)" : "translateX(0)";
    action = (
      <label style={{ position: "relative", display: "inline-block", width: 36, height: 20, cursor: "pointer" }}>
        <input
          type="checkbox"
          checked={info.enabled}
          style={{ opacity: 0, width: 0, height: 0, position: "absolute" }}
          onChange={async (e) => {
            await onToggle(name, e.target.checked);
          }}
        />
        <span style={{ position: "absolute", inset: 0, background: bg, borderRadius: 20, transition: "background 0.2s" }}></span>
        <span style={{
          position: "absolute", height: 14, width: 14, left: 3, bottom: 3,
          background: "#fff", borderRadius: "50%", transition: "transform 0.2s",
          boxShadow: "0 1px 3px rgba(0,0,0,0.15)", transform: knobX,
        }}></span>
      </label>
    );
  }

  // Sub-permissions only render when the connector is actually on; if the
  // user has the connector toggled off there's no point asking them to
  // grant per-folder TCC access.
  const showSubPermissions = !!meta.subPermissions && info.enabled && !info.error;

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 0", borderRadius: 8 }}>
        <div style={{
          width: 28, height: 28, borderRadius: 6, display: "flex", alignItems: "center",
          justifyContent: "center", background: "rgba(199,234,187,0.3)", color: "#84B179", flexShrink: 0,
        }}>
          {icon}
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 12.5, fontWeight: 600 }}>{meta.label}</div>
          <div style={{ fontSize: 11, color: "#9BA896" }}>{meta.desc}</div>
          {info.error && (
            <div style={{ fontSize: 10, color: "#C9594B", marginTop: 2 }}>{info.error}</div>
          )}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
          {action}
        </div>
      </div>
      {showSubPermissions && (
        <div style={{ paddingBottom: 6 }}>
          {meta.subPermissions!.map((sub) => (
            <SubPermissionRow
              key={sub.key}
              permissionKey={sub.key}
              label={sub.label}
              variant="list"
            />
          ))}
        </div>
      )}
    </div>
  );
}
