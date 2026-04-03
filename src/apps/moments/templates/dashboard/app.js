// ── Data ─────────────────────────────────────────────────
// Replace with your actual data.
const DATA = {
  title: "Status Dashboard",
  subtitle: "Last updated April 3, 2026",
  stats: [
    { value: "24", label: "Total", highlight: true },
    { value: "18", label: "Active" },
    { value: "3", label: "Pending" },
    { value: "3", label: "Resolved" },
  ],
  filters: [
    { id: "all", label: "All" },
    { id: "active", label: "Active" },
    { id: "pending", label: "Pending" },
    { id: "resolved", label: "Resolved" },
  ],
  items: [
    {
      title: "Sample Item",
      subtitle: "Source or author",
      description: "Description of this item with relevant details.",
      badges: [{ text: "Active", type: "success" }],
      meta: "March 28, 2026",
      filterKey: "active",
    },
    {
      title: "Another Item",
      subtitle: "Another source",
      description: "More details about this item.",
      badges: [{ text: "Pending", type: "warning" }],
      meta: "March 30, 2026",
      filterKey: "pending",
    },
  ],
};

// ── State ────────────────────────────────────────────────
let activeFilter = "all";
let searchQuery = "";

// ── Render ───────────────────────────────────────────────
function render() {
  document.getElementById("title").textContent = DATA.title;
  document.getElementById("subtitle").textContent = DATA.subtitle;

  // Stats
  document.getElementById("stats").innerHTML = DATA.stats.map(s => `
    <div class="stat-pill${s.highlight ? " highlight" : ""}">
      <div class="stat-value">${s.value}</div>
      <div class="stat-label">${s.label}</div>
    </div>
  `).join("");

  // Filters
  document.getElementById("filters").innerHTML = DATA.filters.map(f => `
    <button class="filter-btn${f.id === activeFilter ? " active" : ""}" data-filter="${f.id}">
      ${f.label}
    </button>
  `).join("");

  renderItems();
}

function renderItems() {
  const q = searchQuery.toLowerCase();
  const filtered = DATA.items.filter(item => {
    if (activeFilter !== "all" && item.filterKey !== activeFilter) return false;
    if (q && !`${item.title} ${item.subtitle} ${item.description}`.toLowerCase().includes(q)) return false;
    return true;
  });

  const container = document.getElementById("items");
  if (filtered.length === 0) {
    container.innerHTML = '<div class="empty">No matching items.</div>';
    return;
  }

  container.innerHTML =
    `<div class="result-count">${filtered.length} item${filtered.length !== 1 ? "s" : ""}</div>` +
    filtered.map((item, i) => `
      <div class="glass-card" style="animation-delay: ${i * 0.03}s">
        <div class="card-header">
          <div>
            <div class="card-title">${item.url ? `<a href="${item.url}" target="_blank">${item.title}</a>` : item.title}</div>
            ${item.subtitle ? `<div class="card-subtitle">${item.subtitle}</div>` : ""}
          </div>
          ${item.badges?.length ? `<div class="card-badges">${item.badges.map(b =>
            `<span class="badge${b.type ? " " + b.type : ""}">${b.text}</span>`).join("")}</div>` : ""}
        </div>
        ${item.description ? `<div class="card-desc">${item.description}</div>` : ""}
        ${item.meta ? `<div class="card-meta">${item.meta}</div>` : ""}
      </div>
    `).join("");
}

// Events
document.getElementById("filters").addEventListener("click", e => {
  const btn = e.target.closest(".filter-btn");
  if (!btn) return;
  activeFilter = btn.dataset.filter;
  render();
});

document.getElementById("search").addEventListener("input", e => {
  searchQuery = e.target.value;
  renderItems();
});

render();
