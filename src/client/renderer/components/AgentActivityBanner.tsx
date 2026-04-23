import React from "react";

interface Props {
  agent: string;
  message: string;
  numTurns: number | null;
  maxTurns: number | null;
}

const AGENT_LABELS: Record<string, string> = {
  memory: "Memory",
  moments_discovery: "Tadas · Discovery",
  moment_run: "Tadas · Run",
  seeker: "Seeker",
};

function prettyAgent(agent: string): string {
  return AGENT_LABELS[agent] ?? agent.replace(/_/g, " ");
}

export function AgentActivityBanner({ agent, message, numTurns, maxTurns }: Props) {
  const showProgress = maxTurns != null && maxTurns > 0;
  const pct = showProgress && numTurns != null
    ? Math.min(100, Math.max(0, (numTurns / maxTurns) * 100))
    : 0;

  return (
    <div className="agent-activity-banner">
      <div className="agent-activity-row">
        <div className="agent-activity-spinner" />
        <span className="agent-activity-label">{prettyAgent(agent)}</span>
        <span className="agent-activity-text">{message}</span>
        {showProgress && numTurns != null && (
          <span className="agent-activity-count">{Math.round(pct)}%</span>
        )}
      </div>
      {showProgress && (
        <div className="agent-activity-progress-track">
          <div className="agent-activity-progress-fill" style={{ width: `${pct}%` }} />
        </div>
      )}
    </div>
  );
}
