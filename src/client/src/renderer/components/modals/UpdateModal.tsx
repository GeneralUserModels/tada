interface Props {
  version: string;
  onDismiss: () => void;
}

export function UpdateModal({ version, onDismiss }: Props) {
  const handleInstallNow = () => {
    onDismiss();
    window.powernap.installNow();
  };

  const handleNextLaunch = () => {
    window.powernap.installOnNextLaunch();
    onDismiss();
  };

  const handleLater = () => {
    window.powernap.dismissUpdate();
    onDismiss();
  };

  return (
    <div className="update-modal-overlay" style={{ display: "flex" }}>
      <div className="update-modal">
        <div className="update-modal-title">Update Ready</div>
        <div className="update-modal-message">
          Version {version} has been downloaded and is ready to install.
        </div>
        <div className="update-modal-actions">
          <button className="pill-btn pill-start" onClick={handleInstallNow}>
            Install Now
          </button>
          <button className="pill-btn" onClick={handleNextLaunch}>
            Next Launch
          </button>
          <button className="update-dismiss" onClick={handleLater}>
            Later
          </button>
        </div>
      </div>
    </div>
  );
}
