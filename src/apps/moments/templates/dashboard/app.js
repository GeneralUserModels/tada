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

// ── App ─────────────────────────────────────────────────
const h = React.createElement;
const { useState } = React;
const { PageHeader, StatRow, FilterBar, SearchInput, ResultCount, ItemCard, EmptyState, useFilter, useSearch } = PN;

function DashboardApp() {
  const [activeFilter, setActiveFilter] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");

  const filtered = useFilter(DATA.items, "filterKey", activeFilter);
  const results = useSearch(filtered, ["title", "subtitle", "description"], searchQuery);

  return h("div", { className: "container" },
    h(PageHeader, { title: DATA.title, subtitle: DATA.subtitle }),
    h(StatRow, { stats: DATA.stats }),
    h("div", { className: "controls" },
      h(FilterBar, { filters: DATA.filters, active: activeFilter, onChange: setActiveFilter }),
      h(SearchInput, { value: searchQuery, onChange: setSearchQuery })
    ),
    results.length === 0
      ? h(EmptyState, { message: "No matching items." })
      : h("div", null,
          h(ResultCount, { count: results.length }),
          results.map(function(item, i) {
            return h(ItemCard, {
              key: i,
              title: item.title,
              subtitle: item.subtitle,
              description: item.description,
              badges: item.badges,
              meta: item.meta,
              url: item.url,
              delay: i * 0.03
            });
          })
        )
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(h(DashboardApp));
