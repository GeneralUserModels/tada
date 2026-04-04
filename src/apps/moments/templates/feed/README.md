# Feed Template

Tabbed content stream with scrollable cards, tags, and scores. Good for lists of items to browse — articles, alerts, notifications, research papers.

## DATA Schema

```js
const DATA = {
  title: "Feed Title",
  subtitle: "Updated ...",
  tags: ["Tag1", "Tag2"],      // optional — header badges
  stats: [
    { value: "12", label: "Papers" },
  ],
  tabs: [
    {
      id: "papers", label: "Papers",
      items: [
        {
          title: "Item Title",
          url: "https://...",          // optional — makes title a link
          meta: "Author — Source",     // optional
          summary: "Description...",   // optional
          score: 9,                    // optional — shows score circle
          tags: ["tag1", "tag2"],      // optional — small tag pills
        },
      ],
    },
  ],
};
```

## Components Used

- `PN.PageHeader` — title + subtitle + optional tag badges
- `PN.StatRow` — metrics row
- `PN.TabBar` — tab navigation with item counts
- `PN.GlassCard` — card container
- `PN.EmptyState` — no items message

## Template-Specific Components

- `ScoreCircle` — circular score indicator (green when >= 8)
- `FeedCard` — card with title, meta, summary, score, and tag pills
