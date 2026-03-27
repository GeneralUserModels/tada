interface Props {
  labels: number;
  step: number;
}

export function StatusBar({ labels, step }: Props) {
  return (
    <div className="status-bar">
      <div className="stat-pill" title="Screen events captured as training labels">
        <span className="stat-label">Labels</span>
        <span className="stat-value">{labels}</span>
      </div>
      <div className="stat-pill" title="Training steps completed">
        <span className="stat-label">Step</span>
        <span className="stat-value">{step}</span>
      </div>
    </div>
  );
}
