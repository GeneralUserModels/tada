import { useEffect, useState } from "react";
import { useAppContext } from "../../context/AppContext";
import { useMoments } from "../../hooks/useMoments";
import { getServerUrl } from "../../api/client";

export function TadaView() {
  const { state } = useAppContext();
  const { results, loading, load } = useMoments();
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null);
  const [resultUrl, setResultUrl] = useState<string | null>(null);

  useEffect(() => {
    if (state.connected) load();
  }, [state.connected, load]);

  const handleCardClick = (slug: string) => {
    setSelectedSlug(slug);
    setResultUrl(`${getServerUrl()}/api/moments/results/${slug}/index.html`);
  };

  // Detail view: iframe loading agent-generated HTML from server
  if (selectedSlug && resultUrl) {
    const selected = results.find((r) => r.slug === selectedSlug);
    return (
      <div id="tada-view" className="view active">
        <div className="tada-detail-header">
          <button className="tada-back-btn" onClick={() => { setSelectedSlug(null); setResultUrl(null); }}>
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M9 2L4 7l5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            Back
          </button>
          {selected && <span className="tada-detail-title">{selected.title}</span>}
        </div>
        <div className="tada-detail glass-card">
          <iframe
            src={resultUrl}
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
            </div>
            <div className="tada-card-schedule">
              <span className="tada-card-frequency">{r.frequency}</span>
              <span className="tada-card-time">{r.schedule}</span>
              <span className="tada-card-date">{new Date(r.completed_at).toLocaleDateString()}</span>
            </div>
            <p className="tada-card-desc">{r.description}</p>
          </section>
        ))
      )}
    </div>
  );
}
