import React from "react";

const DOWNLOAD_URL = "https://github.com/GeneralUserModels/tada-release/releases/latest";

interface Props {
  version: string;
  onDismiss: () => void;
}

export function UpdateBanner({ version, onDismiss }: Props) {
  return (
    <div className="update-banner">
      <span className="update-banner-text">
        Version {version} is available.
      </span>
      <a
        className="pill-btn pill-start update-banner-link"
        href={DOWNLOAD_URL}
        target="_blank"
        rel="noopener noreferrer"
      >
        Download
      </a>
      <button className="update-banner-dismiss" onClick={onDismiss}>
        Dismiss
      </button>
    </div>
  );
}
