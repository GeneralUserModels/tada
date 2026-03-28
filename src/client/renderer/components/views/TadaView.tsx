import { useEffect, useState } from "react";
import { useAppContext } from "../../context/AppContext";

export function TadaView() {
  const { state } = useAppContext();
  const [results, setResults] = useState<MomentResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null);
  const [resultHtml, setResultHtml] = useState<string | null>(null);

  useEffect(() => {
    if (state.connected) {
      window.powernap.getMomentsResults().then((res) => {
        setResults(res);
        setLoading(false);
      }).catch(() => setLoading(false));
    }
  }, [state.connected]);

  // Keep in sync with live completions
  useEffect(() => {
    setResults(state.momentResults);
  }, [state.momentResults]);

  const handleCardClick = async (slug: string) => {
    const html = await window.powernap.getMomentResultHtml(slug);
    setSelectedSlug(slug);
    setResultHtml(html);
  };

  // Detail view: iframe showing agent-generated HTML via srcdoc
  if (selectedSlug && resultHtml) {
    const selected = results.find((r) => r.slug === selectedSlug);
    return (
      <div id="tada-view" className="view active">
        <div className="tada-detail-header">
          <button className="tada-back-btn" onClick={() => { setSelectedSlug(null); setResultHtml(null); }}>
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M9 2L4 7l5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            Back
          </button>
          {selected && <span className="tada-detail-title">{selected.title}</span>}
        </div>
        <div className="tada-detail glass-card">
          <iframe
            srcDoc={resultHtml}
            sandbox="allow-scripts"
            style={{ width: "100%", height: "100%", border: "none", borderRadius: "var(--r-md)" }}
          />
        </div>
      </div>
    );
  }

  // List view
  return (
    <div id="tada-view" className="view active">
      <section className="glass-card">
        <div className="card-header">
          <h2>Ta-Da</h2>
          <span style={{ fontSize: 11, color: "var(--text-tertiary)" }}>
            {results.length} completed
          </span>
        </div>
      </section>

      {loading ? (
        <div style={{ color: "var(--text-tertiary)", fontSize: 12, padding: 12 }}>Loading...</div>
      ) : results.length === 0 ? (
        <div style={{ color: "var(--text-tertiary)", fontSize: 12, padding: 12 }}>
          No completed moments yet. They will appear here as the agent completes tasks.
        </div>
      ) : (
        results.map((r) => (
          <section key={r.slug} className="glass-card tada-card" onClick={() => handleCardClick(r.slug)}>
            <div className="tada-card-header">
              <h3 className="tada-card-title">{r.title}</h3>
              <span className="tada-card-badge">{r.frequency}</span>
            </div>
            <p className="tada-card-desc">{r.description}</p>
            <div className="tada-card-meta">
              <span>{r.schedule}</span>
              <span>{new Date(r.completed_at).toLocaleDateString()}</span>
            </div>
          </section>
        ))
      )}
    </div>
  );
}
