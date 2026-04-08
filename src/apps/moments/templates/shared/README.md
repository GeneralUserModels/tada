# Tada Moments — Shared Component Library

React 18 component library for building moment interfaces. No JSX or build step required — uses `React.createElement` via the `h` shorthand.

## Setup

Every template's `index.html` loads these in order:

```html
<link rel="stylesheet" href="../shared/base.css">
<link rel="stylesheet" href="styles.css">
<script src="https://unpkg.com/react@18/umd/react.production.min.js" crossorigin></script>
<script src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js" crossorigin></script>
<script src="../shared/components.js"></script>
<script src="app.js"></script>
```

When copying to an output directory, place `base.css` and `components.js` as siblings and update paths.

## Component API

All components are on the global `PN` object. Use with `const h = React.createElement`.

### `PN.PageHeader`
Page title with optional subtitle, badges, and status indicator.
```js
h(PN.PageHeader, {
  title: "Dashboard",           // required
  subtitle: "Updated today",    // optional
  badges: ["Tag1", "Tag2"],     // optional — array of strings or {text, type}
  status: { text: "OK", type: "success" }  // optional — type: success|warning|danger|info
})
```

### `PN.GlassCard`
Frosted glass container. The primary layout element.
```js
h(PN.GlassCard, {
  delay: 0.04,      // optional — fadeSlideIn animation delay in seconds
  className: "",     // optional — extra CSS classes
  style: {},         // optional — inline styles
  onClick: fn        // optional — click handler
}, children)
```

### `PN.Badge`
Pill-shaped label.
```js
h(PN.Badge, { text: "Active", type: "success" })
// type: null (default sage) | "success" | "warning" | "danger"
```

### `PN.BadgeRow`
Flex row of badges.
```js
h(PN.BadgeRow, { badges: [{ text: "New", type: "success" }, { text: "Urgent", type: "danger" }] })
// badges can also be plain strings: ["Tag1", "Tag2"]
```

### `PN.StatRow`
Horizontal row of stat pills for metrics.
```js
h(PN.StatRow, { stats: [
  { value: "24", label: "Total", highlight: true },
  { value: "18", label: "Active" },
]})
```

### `PN.SearchInput`
Controlled search input field.
```js
h(PN.SearchInput, {
  value: query,               // current value
  onChange: setQuery,          // called with string value
  placeholder: "Search...",   // optional
  style: { width: "200px" }   // optional
})
```

### `PN.FilterBar`
Row of pill-style filter buttons.
```js
h(PN.FilterBar, {
  filters: [{ id: "all", label: "All" }, { id: "active", label: "Active" }],
  active: "all",        // currently selected filter id
  onChange: setFilter    // called with filter id
})
```

### `PN.TabBar`
Tab navigation bar.
```js
h(PN.TabBar, {
  tabs: [{ id: "papers", label: "Papers", count: 12 }],
  active: "papers",
  onChange: setTab
})
```

### `PN.ItemCard`
Content card with title, optional subtitle, description, badges, and meta line.
```js
h(PN.ItemCard, {
  title: "Item Name",
  subtitle: "Source",          // optional
  description: "Details...",   // optional
  badges: [{ text: "New" }],  // optional
  meta: "March 28, 2026",     // optional
  url: "https://...",          // optional — makes title a link
  delay: 0.03                  // optional — animation delay
})
```

### `PN.EmptyState`
Empty state placeholder message.
```js
h(PN.EmptyState, { message: "No results found." })
```

### `PN.ResultCount`
Item/row count display.
```js
h(PN.ResultCount, { count: 12 })              // "12 items"
h(PN.ResultCount, { count: 5, total: 48 })    // "5 of 48 rows"
```

## Hooks

### `PN.useFilter(items, key, activeFilter)`
Filters an array by matching `item[key] === activeFilter`. Returns all items when filter is `"all"`.

### `PN.useSearch(items, fields, query)`
Searches items by checking if query appears in any of the named fields. Case-insensitive.

## Design System (base.css)

CSS variables available in all templates:

| Variable | Value | Usage |
|---|---|---|
| `--sage` | `#84B179` | Primary green |
| `--fern` | `#A2CB8B` | Secondary green |
| `--mint` | `#C7EABB` | Light green |
| `--cream` | `#E8F5BD` | Lightest green |
| `--bg` | `#F4F2EE` | Page background |
| `--glass` | `rgba(255,255,255,0.55)` | Glass card background |
| `--text` | `#2C3A28` | Primary text |
| `--text-secondary` | `#6B7A65` | Secondary text |
| `--text-tertiary` | `#9BA896` | Tertiary/meta text |
| `--r-sm/md/lg/xl` | `8/14/20/26px` | Border radii |

Key CSS classes: `.glass-card`, `.badge`, `.stat-row`, `.stat-pill`, `.pill-btn`, `.search-input`, `.result-count`, `.empty`, `.card-header`, `.card-title`, `.card-desc`, `.card-meta`, `.card-badges`.
