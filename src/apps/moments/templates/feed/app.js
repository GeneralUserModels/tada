// ── Data ─────────────────────────────────────────────────
// Replace with your actual data. Each tab contains a list of items.
const DATA = {
  title: "Daily Research Digest",
  subtitle: "Updated April 3, 2026",
  tags: ["Machine Learning", "Reasoning", "Agents"],
  stats: [
    { value: "12", label: "Papers" },
    { value: "8", label: "Threads" },
    { value: "3", label: "Posts" },
  ],
  tabs: [
    {
      id: "papers", label: "Papers",
      items: [
        {
          title: "Sample Paper Title",
          url: "https://arxiv.org/abs/2403.00000",
          meta: "Chen et al. — arXiv, Mar 2026",
          summary: "A brief summary of what this paper covers and why it is relevant.",
          score: 9,
          tags: ["reasoning", "agents"],
        },
        {
          title: "Another Paper Title",
          url: "https://arxiv.org/abs/2403.00001",
          meta: "Smith et al. — NeurIPS 2026",
          summary: "Another summary describing the contribution.",
          score: 7,
          tags: ["training"],
        },
      ],
    },
    {
      id: "threads", label: "Threads",
      items: [
        {
          title: "@researcher — Interesting findings on...",
          url: "https://x.com/researcher/status/123",
          meta: "2h ago — 1.2k likes",
          summary: "Key takeaway from this thread about recent developments.",
          score: 8,
          tags: ["discussion"],
        },
      ],
    },
  ],
};

// ── Render ───────────────────────────────────────────────
let activeTab = DATA.tabs[0]?.id;

function render() {
  document.getElementById("title").textContent = DATA.title;
  document.getElementById("subtitle").textContent = DATA.subtitle;

  // Tags
  document.getElementById("tags").innerHTML =
    (DATA.tags || []).map(t => `<span class="badge">${t}</span>`).join("");

  // Stats
  document.getElementById("stats").innerHTML =
    (DATA.stats || []).map(s => `
      <div class="stat-pill">
        <div class="stat-value">${s.value}</div>
        <div class="stat-label">${s.label}</div>
      </div>
    `).join("");

  // Tabs
  document.getElementById("tab-bar").innerHTML =
    DATA.tabs.map(t => `
      <button class="tab-btn${t.id === activeTab ? " active" : ""}" data-tab="${t.id}">
        ${t.label} (${t.items.length})
      </button>
    `).join("");

  // Content
  const tab = DATA.tabs.find(t => t.id === activeTab);
  if (!tab || tab.items.length === 0) {
    document.getElementById("tab-content").innerHTML = '<div class="empty">No items yet.</div>';
    return;
  }

  document.getElementById("tab-content").innerHTML = tab.items.map((item, i) => `
    <div class="glass-card" style="animation-delay: ${i * 0.04}s">
      <div class="card-header">
        <div>
          <div class="card-title">${item.url ? `<a href="${item.url}" target="_blank">${item.title}</a>` : item.title}</div>
          <div class="card-meta">${item.meta || ""}</div>
        </div>
        ${item.score != null ? `<div class="score${item.score >= 8 ? " high" : ""}">${item.score}</div>` : ""}
      </div>
      ${item.summary ? `<div class="card-summary">${item.summary}</div>` : ""}
      ${item.tags?.length ? `<div class="card-tags">${item.tags.map(t => `<span class="card-tag">${t}</span>`).join("")}</div>` : ""}
    </div>
  `).join("");
}

// Tab switching
document.getElementById("tab-bar").addEventListener("click", e => {
  const btn = e.target.closest(".tab-btn");
  if (!btn) return;
  activeTab = btn.dataset.tab;
  render();
});

render();
