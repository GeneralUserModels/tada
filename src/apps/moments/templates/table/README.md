# Table Template

Sortable, filterable data table with expandable rows. Good for structured data, logs, inventories.

## DATA Schema

```js
const DATA = {
  title: "Table Title",
  subtitle: "Scanned ...",
  stats: [
    { value: "48", label: "Packages" },
  ],
  columns: [
    { key: "name", label: "Name", sortable: true },
    { key: "status", label: "Status", sortable: true },
  ],
  rows: [
    { name: "react", status: "current", detail: "No issues." },  // detail is optional
  ],
};
```

## Components Used

- `PN.PageHeader` — title + subtitle
- `PN.StatRow` — metrics row
- `PN.SearchInput` — search field
- `PN.Badge` — status badges in cells
- `PN.GlassCard` — table container
- `PN.ResultCount` — "N of M rows" counter

## Template-Specific Components

- `SortableHeader` — clickable column headers with sort direction arrows
- `TableRow` — data row with optional expandable detail row
