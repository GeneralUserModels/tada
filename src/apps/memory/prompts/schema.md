# Memory Wiki Schema

Normal wiki pages are markdown files under this directory, excluding `index.md`, `log.md`, `schema.md`, hidden files, and checkpoint files.

Every normal page must start with YAML frontmatter:

```yaml
---
title: <Page Title>
confidence: <0.0-1.0>
last_updated: <YYYY-MM-DD>
---
```

Use natural page titles, confidence scores, and `[[wiki-links]]` for cross-references. Use inline confidence annotations like `[c:0.7]` for important claims. Update existing pages instead of duplicating facts across multiple pages.

`index.md` catalogs pages. `log.md` records dated ingest changes. This file records the conventions the memory ingest agent should follow.
