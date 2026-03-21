interface Props {
  prediction: { actions?: string; error?: string; timestamp?: string } | null;
}

function parseActions(text: string): string[] {
  const matches = text.match(/<action>([\s\S]*?)<\/action>/g);
  if (matches) {
    return matches.map((m) => m.replace(/<\/?action>/g, "").trim());
  }
  return [text.replace(/<[^>]+>/g, "").trim()];
}

export function PredictionCard({ prediction }: Props) {
  let content: JSX.Element;

  if (!prediction) {
    content = <span className="empty-state">Waiting for first prediction...</span>;
  } else if (prediction.error) {
    content = <span className="empty-state">{prediction.error}</span>;
  } else {
    const actions = parseActions(prediction.actions ?? "");
    content = (
      <>
        {actions.map((a, i) => (
          <div key={i} className="action-line">
            <span className="action-num">{i + 1}.</span> {a}
          </div>
        ))}
      </>
    );
  }

  return (
    <section className="glass-card flex-2">
      <div className="card-header">
        <h2>Prediction</h2>
        <span className="card-meta">{prediction?.timestamp ?? ""}</span>
      </div>
      <div className="prediction-body">{content}</div>
    </section>
  );
}
