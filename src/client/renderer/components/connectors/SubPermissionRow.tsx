import React, { useEffect, useState } from "react";

interface Props {
  /** Permission key registered in connectorPermissions (e.g. "folder_desktop"). */
  permissionKey: string;
  /** Display label shown in the row (e.g. "Desktop folder"). */
  label: string;
  /** Optional one-line description shown under the label. */
  desc?: string;
  /**
   * Visual variant.
   * - "card": uses the onboarding `.connector-row` CSS classes so the row
   *   blends into the onboarding ConnectorsStep card.
   * - "list": inline styles matching ConnectorItem (settings view).
   */
  variant?: "card" | "list";
  /**
   * Override the default "Grant Access" click behavior. Pass this to route
   * through the onboarding PermissionModal. When omitted the component
   * directly invokes `requestConnectorPermission` and polls until granted.
   */
  onRequest?: () => void;
  /** Fires once the permission flips from denied to granted. */
  onGranted?: () => void;
}

/**
 * Shared row for an OS-level sub-permission that lives under a parent
 * connector (e.g. each protected folder under "Filesystem"). The row owns
 * its own check/poll lifecycle so callers don't have to thread per-folder
 * state through their props.
 */
export function SubPermissionRow({
  permissionKey,
  label,
  desc,
  variant = "list",
  onRequest,
  onGranted,
}: Props) {
  const [granted, setGranted] = useState(false);
  const [waiting, setWaiting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    window.tada.checkConnectorPermission(permissionKey).then((g) => {
      if (!cancelled) setGranted(g);
    });
    return () => {
      cancelled = true;
    };
  }, [permissionKey]);

  // While waiting, poll until the OS reports the permission as granted.
  // Both flows (modal + direct) converge here, so onGranted fires exactly
  // once even if the modal also detects the grant on its own.
  useEffect(() => {
    if (!waiting || granted) return;
    const id = setInterval(async () => {
      const ok = await window.tada.checkConnectorPermission(permissionKey);
      if (ok) {
        clearInterval(id);
        setGranted(true);
        setWaiting(false);
        onGranted?.();
      }
    }, 1500);
    return () => clearInterval(id);
  }, [waiting, granted, permissionKey, onGranted]);

  function handleClick() {
    setWaiting(true);
    if (onRequest) {
      onRequest();
    } else {
      // Settings flow: kick off the OS prompt directly. The poll above
      // handles the "Granted" transition.
      window.tada.requestConnectorPermission(permissionKey);
    }
  }

  if (variant === "card") {
    return (
      <div className="connector-row sub-connector-row">
        <div className="connector-icon" style={{ visibility: "hidden" }} />
        <div className="connector-info">
          <div className="connector-name" style={{ fontWeight: 500 }}>{label}</div>
          {desc && <div className="connector-desc">{desc}</div>}
        </div>
        <div className="connector-action">
          {granted ? (
            <span className="perm-badge granted">Granted</span>
          ) : (
            <button
              className="btn btn-outline btn-sm"
              disabled={waiting}
              onClick={handleClick}
            >
              {waiting ? "Waiting\u2026" : "Grant Access"}
            </button>
          )}
        </div>
      </div>
    );
  }

  // "list" variant: matches ConnectorItem's inline-style row, but indented.
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 12,
        padding: "6px 0 6px 40px",
        borderRadius: 8,
      }}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 11.5, fontWeight: 500 }}>{label}</div>
        {desc && (
          <div style={{ fontSize: 10.5, color: "#9BA896" }}>{desc}</div>
        )}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
        {granted ? (
          <span
            style={{
              fontSize: 10,
              fontWeight: 600,
              padding: "3px 10px",
              borderRadius: 12,
              background: "rgba(132,177,121,0.2)",
              color: "#84B179",
            }}
          >
            Granted
          </span>
        ) : (
          <button
            className="pill-btn"
            style={{ fontSize: 10, padding: "3px 10px" }}
            disabled={waiting}
            onClick={handleClick}
          >
            {waiting ? "Waiting\u2026" : "Grant Access"}
          </button>
        )}
      </div>
    </div>
  );
}
