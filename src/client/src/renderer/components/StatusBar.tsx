interface Props {
  labels: number;
  queue: number;
  step: number;
  buffer: number;
}

export function StatusBar({ labels, queue, step, buffer }: Props) {
  return (
    <div className="status-bar">
      <div className="stat-pill">
        <span className="stat-label">Labels</span>
        <span className="stat-value">{labels}</span>
      </div>
      <div className="stat-pill">
        <span className="stat-label">Queue</span>
        <span className="stat-value">{queue}</span>
      </div>
      <div className="stat-pill">
        <span className="stat-label">Step</span>
        <span className="stat-value">{step}</span>
      </div>
      <div className="stat-pill">
        <span className="stat-label">Buffer</span>
        <span className="stat-value">{buffer}</span>
      </div>
    </div>
  );
}
