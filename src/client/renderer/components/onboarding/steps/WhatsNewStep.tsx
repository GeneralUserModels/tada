import React from "react";

export type WhatsNewFeature = {
  id: string;
  title: string;
  description: string;
  icon: React.ReactNode;
};

type Props = {
  newFeatures: WhatsNewFeature[];
  onContinue: () => void;
  loading?: boolean;
};

export function WhatsNewStep({ newFeatures, onContinue, loading = false }: Props) {
  return (
    <div className="page active">
      <div className="welcome-brand">
        <div className="welcome-brand-icon" aria-hidden="true">✨</div>
        <span>What's new</span>
      </div>
      <p className="welcome-subtitle">
        Tada has picked up a few new tricks since you last saw it. Quick tour below.
      </p>
      <div className="glass-card">
        <div className="welcome-features">
          {newFeatures.map((feature) => (
            <div className="welcome-feature" key={feature.id}>
              <div className="wf-icon">{feature.icon}</div>
              <div className="wf-body">
                <div className="wf-title">{feature.title}</div>
                {feature.description && (
                  <div className="wf-desc">{feature.description}</div>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
      <div className="btn-row">
        {loading ? (
          <div className="startup-indicator">
            <span className="startup-spinner" />
            <span>Checking for updates…</span>
          </div>
        ) : (
          <div />
        )}
        <button className="btn btn-primary" onClick={onContinue} disabled={loading}>
          Show me
        </button>
      </div>
    </div>
  );
}
