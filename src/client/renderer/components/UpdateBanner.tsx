import React from "react";

interface Props {
  version: string;
  ready: boolean;
  onDismiss: () => void;
}

export function UpdateBanner({ version, ready, onDismiss }: Props) {
  const handleInstall = () => {
    window.tada.installUpdate();
  };

  return (
    <div className="update-banner">
      <span className="update-banner-text">
        {ready
          ? `Version ${version} is ready to install.`
          : `Downloading version ${version}\u2026`}
      </span>
      {ready && (
        <button className="pill-btn pill-start update-banner-link" onClick={handleInstall}>
          Install Now
        </button>
      )}
      <button className="update-banner-dismiss" onClick={onDismiss}>
        Dismiss
      </button>
    </div>
  );
}
