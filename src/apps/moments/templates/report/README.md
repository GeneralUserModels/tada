# Report Template

Linear sections with collapsible content, timeline, and action items. Good for summaries, recaps, advisories, analysis.

## DATA Schema

```js
const DATA = {
  title: "Report Title",
  subtitle: "Generated ...",
  status: { text: "Resolved", type: "success" },  // optional — success|warning|danger|info
  sections: [
    {
      title: "Summary",
      content: "<p>HTML content here.</p>",  // supports HTML (p, ul, li, code, pre)
      collapsed: false,                       // initial state
    },
  ],
  actions: [  // optional
    { title: "Do something", description: "Details...", done: false },
  ],
  timeline: [  // optional
    { date: "Apr 1", title: "Event", description: "What happened." },
  ],
};
```

## Components Used

- `PN.PageHeader` — title + subtitle + optional status badge
- `PN.GlassCard` — section containers

## Template-Specific Components

- `CollapsibleSection` — expandable/collapsible content section with chevron toggle
- `ActionItem` — checkbox-style item with done state and strikethrough
- `Timeline` — vertical timeline with dots, dates, and descriptions
