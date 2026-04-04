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

// ── App ─────────────────────────────────────────────────
const h = React.createElement;
const { useState } = React;
const { PageHeader, StatRow, SearchInput, Badge, ResultCount, GlassCard } = PN;

// Status badge type mapping
var STATUS_TYPES = { current: "success", outdated: "warning", vulnerable: "danger" };

function SortableHeader({ columns, sortKey, sortAsc, onSort }) {
  return h("thead", null,
    h("tr", null,
      columns.map(function(c) {
        var sorted = sortKey === c.key;
        var arrow = sorted ? (sortAsc ? "\u2191" : "\u2193") : "";
        return h("th", {
          key: c.key,
          className: (c.sortable ? "sortable" : "") + (sorted ? " sorted" : ""),
          onClick: c.sortable ? function() { onSort(c.key); } : undefined
        }, c.label, c.sortable ? h("span", { className: "sort-arrow" }, arrow) : null);
      })
    )
  );
}

function TableRow({ row, columns, onToggle, expanded }) {
  var cells = columns.map(function(c) {
    var val = row[c.key] || "";
    return h("td", { key: c.key },
      c.key === "status" ? h(Badge, { text: val, type: STATUS_TYPES[val] }) : val
    );
  });

  return h(React.Fragment, null,
    h("tr", {
      className: "data-row",
      style: { cursor: row.detail ? "pointer" : "default" },
      onClick: row.detail ? onToggle : undefined
    }, cells),
    row.detail ? h("tr", {
      className: "detail-row",
      style: { display: expanded ? "" : "none" }
    }, h("td", { colSpan: columns.length },
      h("div", { className: "row-detail" }, row.detail)
    )) : null
  );
}

function TableApp() {
  var [sortKey, setSortKey] = useState(null);
  var [sortAsc, setSortAsc] = useState(true);
  var [searchQuery, setSearchQuery] = useState("");
  var [expandedRows, setExpandedRows] = useState({});

  function handleSort(key) {
    if (sortKey === key) { setSortAsc(!sortAsc); }
    else { setSortKey(key); setSortAsc(true); }
  }

  function toggleRow(idx) {
    setExpandedRows(function(prev) {
      var next = Object.assign({}, prev);
      next[idx] = !next[idx];
      return next;
    });
  }

  // Filter
  var q = searchQuery.toLowerCase();
  var rows = DATA.rows.filter(function(r) {
    return !q || DATA.columns.some(function(c) {
      return String(r[c.key] || "").toLowerCase().includes(q);
    });
  });

  // Sort
  if (sortKey) {
    rows = rows.slice().sort(function(a, b) {
      var va = String(a[sortKey] || ""), vb = String(b[sortKey] || "");
      return sortAsc ? va.localeCompare(vb) : vb.localeCompare(va);
    });
  }

  return h("div", { className: "container" },
    h(PageHeader, { title: DATA.title, subtitle: DATA.subtitle }),
    h(StatRow, { stats: DATA.stats }),
    h("div", { className: "controls" },
      h(SearchInput, { value: searchQuery, onChange: setSearchQuery })
    ),
    h(GlassCard, { className: "table-wrap" },
      h("table", null,
        h(SortableHeader, { columns: DATA.columns, sortKey: sortKey, sortAsc: sortAsc, onSort: handleSort }),
        h("tbody", null,
          rows.map(function(r, i) {
            return h(TableRow, {
              key: i, row: r, columns: DATA.columns,
              expanded: !!expandedRows[i],
              onToggle: function() { toggleRow(i); }
            });
          })
        )
      )
    ),
    h(ResultCount, { count: rows.length, total: DATA.rows.length })
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(h(TableApp));
