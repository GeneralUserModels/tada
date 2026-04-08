/**
 * Tada Moments — Shared React Component Library
 *
 * All components are exposed on the global `PN` namespace.
 * Uses React.createElement (no JSX, no Babel needed).
 *
 * Usage in a template's app.js:
 *   const { PageHeader, GlassCard, Badge, StatRow } = PN;
 *   const App = () => h("div", { className: "container" },
 *     h(PageHeader, { title: DATA.title, subtitle: DATA.subtitle }),
 *     h(StatRow, { stats: DATA.stats }),
 *     h(GlassCard, null, h("p", null, "Hello world"))
 *   );
 *   ReactDOM.createRoot(document.getElementById("root")).render(h(App));
 */

const h = React.createElement;
const { useState, useCallback, useMemo, useEffect } = React;

// ── Components ────────────────────────���─────────────────

/** Page header with title, subtitle, optional badges and status badge */
function PageHeader({ title, subtitle, badges, status }) {
  return h("header", { style: { marginBottom: "16px" } },
    h("div", { style: { display: "flex", alignItems: "center", gap: "12px", marginBottom: "4px" } },
      h("h1", null, title),
      status ? h("span", {
        className: "badge " + (status.type || ""),
        style: { fontSize: "10px", padding: "3px 10px" }
      }, status.text) : null
    ),
    subtitle ? h("p", { className: "meta" }, subtitle) : null,
    badges && badges.length ? h("div", { style: { display: "flex", flexWrap: "wrap", gap: "6px", marginTop: "8px" } },
      badges.map((b, i) => h(Badge, { key: i, text: typeof b === "string" ? b : b.text, type: typeof b === "string" ? null : b.type }))
    ) : null
  );
}

/** Glass card container with optional animation delay */
function GlassCard({ children, className, style, delay, onClick }) {
  const s = Object.assign({}, delay != null ? { animationDelay: delay + "s" } : {}, style);
  return h("div", {
    className: "glass-card" + (className ? " " + className : ""),
    style: Object.keys(s).length ? s : undefined,
    onClick: onClick
  }, children);
}

/** Single badge pill */
function Badge({ text, type }) {
  return h("span", { className: "badge" + (type ? " " + type : "") }, text);
}

/** Row of badges */
function BadgeRow({ badges }) {
  if (!badges || !badges.length) return null;
  return h("div", { className: "card-badges" },
    badges.map((b, i) => h(Badge, { key: i, text: b.text || b, type: b.type }))
  );
}

/** Stats row with stat pills */
function StatRow({ stats }) {
  if (!stats || !stats.length) return null;
  return h("div", { className: "stat-row" },
    stats.map((s, i) => h(StatPill, { key: i, value: s.value, label: s.label, highlight: s.highlight }))
  );
}

/** Single stat pill */
function StatPill({ value, label, highlight }) {
  return h("div", { className: "stat-pill" + (highlight ? " highlight" : "") },
    h("div", { className: "stat-value" }, value),
    h("div", { className: "stat-label" }, label)
  );
}

/** Controlled search input */
function SearchInput({ value, onChange, placeholder, className, style }) {
  return h("input", {
    type: "text",
    className: "search-input" + (className ? " " + className : ""),
    style: style,
    placeholder: placeholder || "Search...",
    value: value,
    onChange: function(e) { onChange(e.target.value); }
  });
}

/** Filter bar with pill buttons */
function FilterBar({ filters, active, onChange }) {
  return h("div", { style: { display: "flex", gap: "4px", flexWrap: "wrap" } },
    filters.map(function(f) {
      return h("button", {
        key: f.id,
        className: "pill-btn" + (f.id === active ? " active" : ""),
        onClick: function() { onChange(f.id); }
      }, f.label);
    })
  );
}

/** Tab bar with tab buttons */
function TabBar({ tabs, active, onChange }) {
  return h("div", { className: "tab-bar" },
    tabs.map(function(t) {
      return h("button", {
        key: t.id,
        className: "tab-btn" + (t.id === active ? " active" : ""),
        onClick: function() { onChange(t.id); }
      }, t.label + (t.count != null ? " (" + t.count + ")" : ""));
    })
  );
}

/** Content card with title, subtitle, description, badges, meta */
function ItemCard({ title, subtitle, description, badges, meta, url, delay, onClick }) {
  return h(GlassCard, { delay: delay, onClick: onClick },
    h("div", { className: "card-header" },
      h("div", null,
        h("div", { className: "card-title" },
          url ? h("a", { href: url, target: "_blank" }, title) : title
        ),
        subtitle ? h("div", { className: "card-subtitle" }, subtitle) : null
      ),
      badges && badges.length ? h(BadgeRow, { badges: badges }) : null
    ),
    description ? h("div", { className: "card-desc" }, description) : null,
    meta ? h("div", { className: "card-meta" }, meta) : null
  );
}

/** Empty state message */
function EmptyState({ message }) {
  return h("div", { className: "empty" }, message || "No items to display.");
}

/** Result count display */
function ResultCount({ count, total }) {
  var text = total != null
    ? count + " of " + total + " rows"
    : count + " item" + (count !== 1 ? "s" : "");
  return h("div", { className: "result-count" }, text);
}

// ── Hooks ───────────────────────────────────────────────

/** Filter items by a key matching the active filter value. "all" returns everything. */
function useFilter(items, key, activeFilter) {
  return useMemo(function() {
    if (!activeFilter || activeFilter === "all") return items;
    return items.filter(function(item) { return item[key] === activeFilter; });
  }, [items, key, activeFilter]);
}

/** Search items across the given fields by query string. */
function useSearch(items, fields, query) {
  return useMemo(function() {
    if (!query) return items;
    var q = query.toLowerCase();
    return items.filter(function(item) {
      return fields.some(function(f) {
        return String(item[f] || "").toLowerCase().includes(q);
      });
    });
  }, [items, fields, query]);
}

// ── Export ───────────────────────────────────────────────

window.PN = {
  // Components
  PageHeader: PageHeader,
  GlassCard: GlassCard,
  Badge: Badge,
  BadgeRow: BadgeRow,
  StatRow: StatRow,
  StatPill: StatPill,
  SearchInput: SearchInput,
  FilterBar: FilterBar,
  TabBar: TabBar,
  ItemCard: ItemCard,
  EmptyState: EmptyState,
  ResultCount: ResultCount,
  // Hooks
  useFilter: useFilter,
  useSearch: useSearch,
};
