import React from "react";

type Props = {
  flag: (name: string) => boolean;
  screenGranted: boolean;
  calendarConnected: boolean;
  outlookConnected: boolean;
  notifAvailable: boolean;
  fsAvailable: boolean;
  accessibilityGranted: boolean;
  browserCookiesGranted: boolean;
  connectingGoogle: string | null;
  connectingOutlook: boolean;
  onBack: () => void;
  onContinue: () => void;
  onOpenPermissionModal: (name: string, onGranted: () => void) => void;
  onConnectGoogle: (svc: string) => void;
  onConnectOutlook: () => void;
  setScreenGranted: (v: boolean) => void;
  setNotifAvailable: (v: boolean) => void;
  setNotifEnabled: (v: boolean) => void;
  setFsAvailable: (v: boolean) => void;
  setFsEnabled: (v: boolean) => void;
  setBrowserCookiesGranted: (v: boolean) => void;
  setAccessibilityGranted: (v: boolean) => void;
  micGranted: boolean;
  setMicGranted: (v: boolean) => void;
  sysAudioGranted: boolean;
  setSysAudioGranted: (v: boolean) => void;
};

export function ConnectorsStep(props: Props) {
  const canContinue = !(
    !props.screenGranted
    || !props.accessibilityGranted
    || (props.flag("permission_browser_cookies") && !props.browserCookiesGranted)
  );

  return (
    <div className="page active">
      <div className="page-icon">
        <svg width="22" height="22" viewBox="0 0 16 16" fill="none"><path d="M6 2v3H3v6h3v3h4v-3h3V5h-3V2H6z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round"/></svg>
      </div>
      <div className="page-title">Connectors</div>
      <p className="page-desc">Choose which data sources Tada can access to learn your patterns.</p>
      <div className="glass-card" style={{ padding: 16 }}>
        <div className="connector-list">
          <div className="connector-row">
            <div className="connector-icon">
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><rect x="2" y="3" width="12" height="10" rx="2" stroke="currentColor" strokeWidth="1.3"/><circle cx="8" cy="8" r="2" fill="currentColor"/></svg>
            </div>
            <div className="connector-info">
              <div className="connector-name">Screen Recording <span className="required-tag">Required</span></div>
              <div className="connector-desc">Captures your screen to observe workflow</div>
            </div>
            <div className="connector-action">
              {props.screenGranted
                ? <span className="perm-badge granted">Granted</span>
                : <button className="btn btn-outline btn-sm" onClick={() => props.onOpenPermissionModal("screen", () => props.setScreenGranted(true))}>Grant Access</button>
              }
            </div>
          </div>

          {props.flag("permission_microphone") && (
            <div className="connector-row">
              <div className="connector-icon">
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><rect x="6" y="1" width="4" height="8" rx="2" stroke="currentColor" strokeWidth="1.3"/><path d="M4 7a4 4 0 008 0" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/><path d="M8 11v3M6 14h4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/></svg>
              </div>
              <div className="connector-info">
                <div className="connector-name">Microphone <span className="optional-tag">optional</span></div>
                <div className="connector-desc">Transcribe your voice in meetings</div>
              </div>
              <div className="connector-action">
                {props.micGranted
                  ? <span className="perm-badge granted">Granted</span>
                  : <button className="btn btn-outline btn-sm" onClick={() => props.onOpenPermissionModal("microphone", () => props.setMicGranted(true))}>Grant Access</button>
                }
              </div>
            </div>
          )}

          {props.flag("permission_system_audio") && (
            <div className="connector-row">
              <div className="connector-icon">
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M2 5.5h2.5L8 2v12l-3.5-3.5H2a1 1 0 01-1-1v-3a1 1 0 011-1z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round"/><path d="M11 5.5a3.5 3.5 0 010 5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/><path d="M13 3.5a6.5 6.5 0 010 9" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/></svg>
              </div>
              <div className="connector-info">
                <div className="connector-name">System Audio <span className="optional-tag">optional</span></div>
                <div className="connector-desc">Transcribe other participants in meetings</div>
              </div>
              <div className="connector-action">
                {props.sysAudioGranted
                  ? <span className="perm-badge granted">Granted</span>
                  : <button className="btn btn-outline btn-sm" onClick={() => props.onOpenPermissionModal("system_audio", () => props.setSysAudioGranted(true))}>Grant Access</button>
                }
              </div>
            </div>
          )}

          {(props.flag("permission_microphone") || props.flag("permission_system_audio")) && (
            <p className="connector-hint">
              Audio is only used when you hit record for meeting notes.
            </p>
          )}

          {(props.flag("connector_gmail") || props.flag("connector_calendar")) && (
            <div className="connector-row">
              <div className="connector-icon">
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><rect x="2" y="3" width="12" height="11" rx="1.5" stroke="currentColor" strokeWidth="1.3"/><path d="M2 6.5h12" stroke="currentColor" strokeWidth="1.3"/><path d="M5 1.5v3M11 1.5v3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/></svg>
              </div>
              <div className="connector-info">
                <div className="connector-name">Google</div>
                <div className="connector-desc">Calendar + Email</div>
              </div>
              <div className="connector-action">
                {props.calendarConnected
                  ? <span className="connected-badge">Connected</span>
                  : <button className="btn btn-outline btn-sm" disabled={props.connectingGoogle === "calendar"} onClick={() => props.onConnectGoogle("calendar")}>{props.connectingGoogle === "calendar" ? "Connecting..." : "Connect"}</button>
                }
              </div>
            </div>
          )}

          {(props.flag("connector_outlook_email") || props.flag("connector_outlook_calendar")) && (
            <div className="connector-row">
              <div className="connector-icon">
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><rect x="2" y="3" width="12" height="11" rx="1.5" stroke="currentColor" strokeWidth="1.3"/><path d="M2 6.5h12" stroke="currentColor" strokeWidth="1.3"/><path d="M5 1.5v3M11 1.5v3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/></svg>
              </div>
              <div className="connector-info">
                <div className="connector-name">Outlook</div>
                <div className="connector-desc">Calendar + Email</div>
              </div>
              <div className="connector-action">
                {props.outlookConnected
                  ? <span className="connected-badge">Connected</span>
                  : <button className="btn btn-outline btn-sm" disabled={props.connectingOutlook} onClick={props.onConnectOutlook}>{props.connectingOutlook ? "Connecting..." : "Connect"}</button>
                }
              </div>
            </div>
          )}

          {props.flag("permission_notifications") && (
            <div className="connector-row">
              <div className="connector-icon">
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M2 4.5V13a1 1 0 001 1h10a1 1 0 001-1V6a1 1 0 00-1-1H7.5L6 3H3a1 1 0 00-1 1.5z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round"/></svg>
              </div>
              <div className="connector-info">
                <div className="connector-name">Disk Access</div>
                <div className="connector-desc">Notifications, Desktop, Documents, Downloads</div>
              </div>
              <div className="connector-action">
                {props.notifAvailable && props.fsAvailable
                  ? <span className="perm-badge granted">Granted</span>
                  : <button className="btn btn-outline btn-sm" onClick={() => props.onOpenPermissionModal("notifications", () => { props.setNotifAvailable(true); props.setNotifEnabled(true); props.setFsAvailable(true); props.setFsEnabled(true); })}>Grant Access</button>
                }
              </div>
            </div>
          )}

          {props.flag("permission_browser_cookies") && (
            <div className="connector-row">
              <div className="connector-icon">
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.3"/><path d="M2 8h12M8 2c-2 2-2 10 0 12M8 2c2 2 2 10 0 12" stroke="currentColor" strokeWidth="1.3"/></svg>
              </div>
              <div className="connector-info">
                <div className="connector-name">Browser Cookies <span className="required-tag">Required</span></div>
                <div className="connector-desc">Let the agent browse the internet</div>
              </div>
              <div className="connector-action">
                {props.browserCookiesGranted
                  ? <span className="perm-badge granted">Granted</span>
                  : <button className="btn btn-outline btn-sm" onClick={() => props.onOpenPermissionModal("browser_cookies", () => props.setBrowserCookiesGranted(true))}>Grant Access</button>
                }
              </div>
            </div>
          )}

          <div className="connector-row">
            <div className="connector-icon">
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M8 1.5a6.5 6.5 0 100 13 6.5 6.5 0 000-13z" stroke="currentColor" strokeWidth="1.3"/><circle cx="8" cy="5.5" r="1" fill="currentColor"/><path d="M5.5 7.5h5M8 7.5v4M6.5 11.5L8 9.5l1.5 2" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round"/></svg>
            </div>
            <div className="connector-info">
              <div className="connector-name">Accessibility <span className="required-tag">Required</span></div>
              <div className="connector-desc">Tab autocomplete (Tabracadabra)</div>
            </div>
            <div className="connector-action">
              {props.accessibilityGranted
                ? <span className="perm-badge granted">Granted</span>
                : <button className="btn btn-outline btn-sm" onClick={() => props.onOpenPermissionModal("accessibility", () => props.setAccessibilityGranted(true))}>Grant Access</button>
              }
            </div>
          </div>
        </div>
      </div>
      <div className="btn-row">
        <button className="btn btn-ghost" onClick={props.onBack}>Back</button>
        <button className="btn btn-primary" disabled={!canContinue} onClick={props.onContinue}>Continue</button>
      </div>
    </div>
  );
}
