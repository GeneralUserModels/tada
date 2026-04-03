// ── Data ─────────────────────────────────────────────────
// Replace with your actual data.
const DATA = {
  title: "Weekly Security Report",
  subtitle: "Generated April 3, 2026",
  status: { text: "Resolved", type: "success" }, // success | warning | danger | info
  sections: [
    {
      title: "Summary",
      content: "<p>A brief overview of the report findings and key takeaways.</p>",
      collapsed: false,
    },
    {
      title: "Details",
      content: "<ul><li>Finding one with relevant context.</li><li>Finding two with impact analysis.</li></ul>",
      collapsed: true,
    },
    {
      title: "Recommendations",
      content: "<p>Specific recommendations based on the analysis above.</p>",
      collapsed: true,
    },
  ],
  actions: [
    { title: "Review findings", description: "Check the detailed analysis for accuracy.", done: true },
    { title: "Update configuration", description: "Apply the recommended changes.", done: false },
    { title: "Monitor for 24h", description: "Watch metrics after applying changes.", done: false },
  ],
  timeline: [
    { date: "Apr 1", title: "Issue detected", description: "Automated monitoring flagged anomaly." },
    { date: "Apr 2", title: "Investigation", description: "Root cause identified and documented." },
    { date: "Apr 3", title: "Resolution", description: "Fix deployed and verified." },
  ],
};

// ── Render ───────────────────────────────────────────────
function render() {
  // Header
  document.getElementById("header").innerHTML = `
    <div class="report-header">
      <div class="header-row">
        <h1>${DATA.title}</h1>
        ${DATA.status ? `<span class="status-badge ${DATA.status.type}">${DATA.status.text}</span>` : ""}
      </div>
      <p class="meta">${DATA.subtitle}</p>
    </div>
  `;

  // Sections
  document.getElementById("sections").innerHTML = DATA.sections.map((s, i) => `
    <div class="glass-card" style="animation-delay: ${i * 0.04}s">
      <button class="collapsible-toggle" aria-expanded="${!s.collapsed}" onclick="toggleSection(this)">
        <span class="section-title">${s.title}</span>
        <span class="chevron">${s.collapsed ? "\u25B6" : "\u25BC"}</span>
      </button>
      <div class="collapsible-body" style="${s.collapsed ? "display:none" : ""}">
        <div class="section-content">${s.content}</div>
      </div>
    </div>
  `).join("");

  // Actions
  if (DATA.actions?.length) {
    const done = DATA.actions.filter(a => a.done).length;
    document.getElementById("actions").innerHTML = `
      <h2 class="actions-header">Action Items (${done}/${DATA.actions.length})</h2>
      ${DATA.actions.map(a => `
        <div class="action-item">
          <div class="action-check${a.done ? " done" : ""}">${a.done ? "\u2713" : ""}</div>
          <div>
            <div class="action-title" style="${a.done ? "text-decoration: line-through; opacity: 0.6" : ""}">${a.title}</div>
            ${a.description ? `<div class="action-desc">${a.description}</div>` : ""}
          </div>
        </div>
      `).join("")}
    `;
  }

  // Timeline
  if (DATA.timeline?.length) {
    document.getElementById("timeline").innerHTML = `
      <h2 class="timeline-header">Timeline</h2>
      <div class="timeline">
        ${DATA.timeline.map(t => `
          <div class="timeline-item">
            <div class="timeline-dot"></div>
            <div class="timeline-date">${t.date}</div>
            <div class="timeline-title">${t.title}</div>
            ${t.description ? `<div class="timeline-desc">${t.description}</div>` : ""}
          </div>
        `).join("")}
      </div>
    `;
  }
}

function toggleSection(btn) {
  const expanded = btn.getAttribute("aria-expanded") === "true";
  btn.setAttribute("aria-expanded", !expanded);
  btn.querySelector(".chevron").textContent = expanded ? "\u25B6" : "\u25BC";
  btn.nextElementSibling.style.display = expanded ? "none" : "";
}

render();
