# Dashboard Template

Stats row + filterable/searchable card grid. Good for metrics, tracking, status overviews.

## DATA Schema

```js
const DATA = {
  title: "Dashboard Title",
  subtitle: "Last updated ...",
  stats: [
    { value: "24", label: "Total", highlight: true },  // highlight is optional
  ],
  filters: [
    { id: "all", label: "All" },
    { id: "active", label: "Active" },
  ],
  items: [
    {
      title: "Item Name",
      subtitle: "Source",           // optional
      description: "Details...",    // optional
      badges: [{ text: "Active", type: "success" }],  // optional
      meta: "March 28, 2026",      // optional
      url: "https://...",           // optional
      filterKey: "active",          // matches filter id
    },
  ],
};
```

## Components Used

- `PN.PageHeader` — title + subtitle
- `PN.StatRow` — metrics row
- `PN.FilterBar` — pill-style filter buttons
- `PN.SearchInput` — search field
- `PN.ResultCount` — "N items" counter
- `PN.ItemCard` — content cards with title, description, badges, meta
- `PN.EmptyState` — no results message
- `PN.useFilter` + `PN.useSearch` — filtering/search hooks
