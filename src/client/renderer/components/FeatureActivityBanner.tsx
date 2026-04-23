import React from "react";
import { AgentActivityInfo } from "../context/AppContext";

interface Props {
  activity: AgentActivityInfo;
  label?: string;
}

export function FeatureActivityBanner({ activity, label }: Props) {
  const showProgress = activity.maxTurns != null && activity.maxTurns > 0;
  const pct = showProgress && activity.numTurns != null
    ? Math.min(100, Math.max(0, (activity.numTurns / activity.maxTurns!) * 100))
    : 0;

  return (
    <div className="feature-activity-banner">
      <div className="feature-activity-row">
        <div className="feature-activity-spinner" />
        {label && <span className="feature-activity-label">{label}</span>}
        <span className="feature-activity-text">{activity.message}</span>
        {showProgress && activity.numTurns != null && (
          <span className="feature-activity-count">{Math.round(pct)}%</span>
        )}
      </div>
      {showProgress && (
        <div className="feature-activity-progress-track">
          <div className="feature-activity-progress-fill" style={{ width: `${pct}%` }} />
        </div>
      )}
    </div>
  );
}
