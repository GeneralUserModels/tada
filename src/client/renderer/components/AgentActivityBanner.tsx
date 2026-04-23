import React from "react";

interface Props {
  message: string;
}

export function AgentActivityBanner({ message }: Props) {
  return (
    <div className="agent-activity-banner">
      <div className="agent-activity-spinner" />
      <span className="agent-activity-text">{message}</span>
    </div>
  );
}
