import { LABELS, RAW_EVENTS, WIKI_PAGES } from "./data";

export type Phase = "ingest" | "twister" | "wiki" | "browse";

export type TimelineEvent =
  | { at: number; kind: "phase"; phase: Phase }
  | { at: number; kind: "rawEvent"; id: string }
  | { at: number; kind: "label"; id: string }
  | { at: number; kind: "createPage"; slug: string }
  | { at: number; kind: "showcase"; slug: string }
  | { at: number; kind: "revealUpdated" }
  | { at: number; kind: "revealUnknown" }
  | { at: number; kind: "enterBrowse" };

const timeline: TimelineEvent[] = [];

// ─── Act 1: Passive ingest — starts immediately ─────────
timeline.push({ at: 0, kind: "phase", phase: "ingest" });
const INGEST_START = 400;
const RAW_SPACING = 800;
RAW_EVENTS.forEach((ev, i) => {
  const at = INGEST_START + i * RAW_SPACING;
  timeline.push({ at, kind: "rawEvent", id: ev.id });
  const label = LABELS.find((l) => l.rawId === ev.id);
  if (label) timeline.push({ at: at + 320, kind: "label", id: label.id });
});

// ─── Act 2: The twister transition ──────────────────────
const INGEST_END = INGEST_START + RAW_EVENTS.length * RAW_SPACING;
timeline.push({ at: INGEST_END + 200, kind: "phase", phase: "twister" });

// ─── Act 3: Wiki accretion ──────────────────────────────
const WIKI_START = INGEST_END + 5000;
timeline.push({ at: WIKI_START, kind: "phase", phase: "wiki" });

const PAGE_CREATION_ORDER: string[] = [
  "interests/journaling",
  "people/toto",
  "people/aunt-em",
  "people/zeke",
  "interests/farm-life",
  "people/scarecrow",
  "people/glinda",
  "people/tin-man",
  "projects/get-home-to-kansas",
  "people/cowardly-lion",
  "people/uncle-henry",
  "people/wizard-of-oz",
  "people/wicked-witch-of-the-west",
];

const PAGE_SPACING = 700;
PAGE_CREATION_ORDER.forEach((slug, i) => {
  timeline.push({ at: WIKI_START + 400 + i * PAGE_SPACING, kind: "createPage", slug });
});

// After all pages exist, cycle through three showcased pages.
const SHOWCASE_AT = WIKI_START + 400 + PAGE_CREATION_ORDER.length * PAGE_SPACING + 400;

// 1) Scarecrow — the fully-fleshed demonstrator (18s).
timeline.push({ at: SHOWCASE_AT, kind: "showcase", slug: "people/scarecrow" });
timeline.push({ at: SHOWCASE_AT + 7500, kind: "revealUpdated" });
timeline.push({ at: SHOWCASE_AT + 12000, kind: "revealUnknown" });

// 2) Get home to Kansas — projects/ page (12s).
const SHOWCASE_2_AT = SHOWCASE_AT + 18000;
timeline.push({ at: SHOWCASE_2_AT, kind: "showcase", slug: "projects/get-home-to-kansas" });

// 3) Wicked Witch — antagonist card with a dramatic [!updated] (13s).
const SHOWCASE_3_AT = SHOWCASE_2_AT + 12000;
timeline.push({ at: SHOWCASE_3_AT, kind: "showcase", slug: "people/wicked-witch-of-the-west" });
timeline.push({ at: SHOWCASE_3_AT + 7500, kind: "revealUpdated" });

// ─── Act 4 — After the third showcase finishes, hand off to interactive
// browse mode. No end card, no graph — the user gets the fully-indexed wiki
// to click through.
const BROWSE_AT = SHOWCASE_3_AT + 13000;
timeline.push({ at: BROWSE_AT, kind: "phase", phase: "browse" });
timeline.push({ at: BROWSE_AT, kind: "enterBrowse" });

export const TIMELINE: TimelineEvent[] = timeline
  .slice()
  .sort((a, b) => a.at - b.at);

export const TIMELINE_DURATION_MS = BROWSE_AT + 500;

// Sanity: every page we create must exist in WIKI_PAGES.
for (const slug of PAGE_CREATION_ORDER) {
  if (!WIKI_PAGES[slug]) throw new Error(`timeline references missing page: ${slug}`);
}
