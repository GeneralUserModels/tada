import React from "react";

interface Props {
  version: string;
  progress: number | null;
  ready: boolean;
  installing: boolean;
  error: string | null;
  onInstall: () => void;
  onDismiss: () => void;
}

export function UpdateBanner({ version, progress, ready, installing, error, onInstall, onDismiss }: Props) {
  const handleInstall = () => {
    onInstall();
    window.tada.installUpdate();
  };

  const pct = progress != null ? Math.round(progress) : 0;
  const downloading = !ready && !error;
  const showBar = downloading && progress != null;

  let statusText: string;
  if (error) {
    statusText = `Update failed — ${error}`;
  } else if (installing) {
    statusText = `Installing version ${version}…`;
  } else if (ready) {
    statusText = `Version ${version} is ready to install.`;
  } else if (progress != null) {
    statusText = `Downloading ${version} — ${pct}%`;
  } else {
    statusText = `Downloading version ${version}…`;
  }

  return (
    <div className={`update-banner${error ? " update-banner--error" : ""}`}>
      <div className="update-banner-content">
        <span className="update-banner-text">{statusText}</span>

        {showBar && (
          <div className="update-progress-track">
            <div
              className="update-progress-fill"
              style={{ width: `${pct}%` }}
            />
          </div>
        )}

        {installing && (
          <div className="update-installing-spinner" />
        )}
      </div>

      <div className="update-banner-actions">
        {ready && !installing && (
          <button className="pill-btn pill-start update-banner-link" onClick={handleInstall}>
            Install Now
          </button>
        )}
        {!installing && (
          <button className="update-banner-dismiss" onClick={onDismiss}>
            Dismiss
          </button>
        )}
      </div>
    </div>
  );
}
