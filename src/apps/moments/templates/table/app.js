// ── Data ─────────────────────────────────────────────────
// Replace with your actual data. Each column defines a key + label.
const DATA = {
  title: "Dependency Inventory",
  subtitle: "Scanned April 3, 2026",
  stats: [
    { value: "48", label: "Packages" },
    { value: "3", label: "Outdated" },
    { value: "1", label: "Vulnerable" },
  ],
  columns: [
    { key: "name", label: "Name", sortable: true },
    { key: "version", label: "Version", sortable: true },
    { key: "status", label: "Status", sortable: true },
    { key: "license", label: "License" },
  ],
  rows: [
    { name: "react", version: "19.1.0", status: "current", license: "MIT", detail: "No issues found." },
    { name: "lodash", version: "4.17.20", status: "outdated", license: "MIT", detail: "Latest: 4.17.21. Minor patch." },
    { name: "express", version: "4.18.2", status: "vulnerable", license: "MIT", detail: "CVE-2024-1234: path traversal in static middleware." },
  ],
};

// ── State ────────────────────────────────────────────────
let sortKey = null;
let sortAsc = true;
let searchQuery = "";

// ── Helpers ──────────────────────────────────────────────
function statusBadge(status) {
  const types = { current: "success", outdated: "warning", vulnerable: "danger" };
  return `<span class="badge ${types[status] || ""}">${status}</span>`;
}

// ── Render ───────────────────────────────────────────────
function render() {
  document.getElementById("title").textContent = DATA.title;
  document.getElementById("subtitle").textContent = DATA.subtitle;

  document.getElementById("stats").innerHTML = DATA.stats.map(s => `
    <div class="stat-pill">
      <div class="stat-value">${s.value}</div>
      <div class="stat-label">${s.label}</div>
    </div>
  `).join("");

  renderTable();
}

function renderTable() {
  const q = searchQuery.toLowerCase();
  let rows = DATA.rows.filter(r =>
    !q || DATA.columns.some(c => String(r[c.key] || "").toLowerCase().includes(q))
  );

  if (sortKey) {
    rows = [...rows].sort((a, b) => {
      const va = String(a[sortKey] || ""), vb = String(b[sortKey] || "");
      return sortAsc ? va.localeCompare(vb) : vb.localeCompare(va);
    });
  }

  // Header
  document.getElementById("thead").innerHTML = "<tr>" + DATA.columns.map(c => {
    const sorted = sortKey === c.key;
    const arrow = sorted ? (sortAsc ? "\u2191" : "\u2193") : "";
    return `<th class="${c.sortable ? "sortable" : ""}${sorted ? " sorted" : ""}" data-key="${c.key}">
      ${c.label}${c.sortable ? `<span class="sort-arrow">${arrow}</span>` : ""}
    </th>`;
  }).join("") + "</tr>";

  // Body
  document.getElementById("tbody").innerHTML = rows.map(r => {
    const cells = DATA.columns.map(c => {
      const val = r[c.key] || "";
      return `<td>${c.key === "status" ? statusBadge(val) : val}</td>`;
    }).join("");
    const detail = r.detail ? `<tr class="detail-row" style="display:none"><td colspan="${DATA.columns.length}"><div class="row-detail">${r.detail}</div></td></tr>` : "";
    return `<tr class="data-row" style="cursor:${r.detail ? "pointer" : "default"}">${cells}</tr>${detail}`;
  }).join("");

  document.getElementById("count").textContent = `${rows.length} of ${DATA.rows.length} rows`;
}

// Sort
document.getElementById("thead").addEventListener("click", e => {
  const th = e.target.closest("th.sortable");
  if (!th) return;
  const key = th.dataset.key;
  if (sortKey === key) { sortAsc = !sortAsc; } else { sortKey = key; sortAsc = true; }
  renderTable();
});

// Row expand
document.getElementById("tbody").addEventListener("click", e => {
  const row = e.target.closest("tr.data-row");
  if (!row) return;
  const detail = row.nextElementSibling;
  if (detail?.classList.contains("detail-row")) {
    detail.style.display = detail.style.display === "none" ? "" : "none";
  }
});

// Search
document.getElementById("search").addEventListener("input", e => {
  searchQuery = e.target.value;
  renderTable();
});

render();
