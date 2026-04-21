import React, { useMemo, useState } from "react";
import { confidenceColor, confidenceLabel } from "../../views/pensieveHelpers";

type SamplePage = {
  path: string;
  title: string;
  category: string;
  confidence: number;
  last_updated: string;
  markdown: string;
};

const SAMPLE_PAGES: SamplePage[] = [
  {
    path: "people/hermione-granger",
    title: "Hermione Granger",
    category: "people",
    confidence: 0.94,
    last_updated: "1997-10-19",
    markdown: `# Hermione Granger

Closest friend since first year. Muggle-born, top of the class in every subject, and the person most likely to have already read the book before it's brought up.

## What she's working on

- Planning the route through the [[Horcrux Hunt]] — she's the one keeping the itinerary.
- Quiet research into house-elf rights (not speaking much about it this year).

## Recent shape

- Carrying a beaded bag full of supplies, books, and the tent.
- Short-tempered whenever [[Defense Against the Dark Arts]] comes up — still angry about last year's curriculum.`,
  },
  {
    path: "projects/horcrux-hunt",
    title: "Horcrux Hunt",
    category: "projects",
    confidence: 0.91,
    last_updated: "1997-11-02",
    markdown: `# Horcrux Hunt

The open undertaking after Dumbledore's funeral. Seven fragments of Voldemort's soul hidden in objects; destroy them all before the final confrontation. [[Hermione Granger]] is keeping the plan.

## Confirmed

- Tom Riddle's diary — destroyed, second year.
- Marvolo's ring — destroyed by Dumbledore; the curse is what killed him.
- Slytherin's locket — recovered from Grimmauld Place, not yet destroyed.

## Still open

- The count is a working assumption, not a certainty.
- Hogwarts itself may hide one (Ravenclaw's diadem is the best guess).
- Nagini is almost certainly one, and she travels with Voldemort.`,
  },
  {
    path: "interests/defense-against-the-dark-arts",
    title: "Defense Against the Dark Arts",
    category: "interests",
    confidence: 0.82,
    last_updated: "1997-09-28",
    markdown: `# Defense Against the Dark Arts

Strongest subject, and the one worth returning to. Started with Lupin in third year; a new teacher each year has meant piecing most of it together alone.

## Recurring threads

- Patronus charm — the piece that holds up when things go wrong.
- Non-verbal spellwork — came up again planning the [[Horcrux Hunt]] with [[Hermione Granger]].
- Spotting dark objects before touching them (the locket was a lesson).

## Open questions

- How much of the Elder Wand folklore is real?
- Is there a real counter to the Killing Curse, or is "love" the whole answer?`,
  },
  {
    path: "notes/suspicions-about-snape",
    title: "Suspicions about Snape",
    category: "notes",
    confidence: 0.58,
    last_updated: "1997-10-11",
    markdown: `# Suspicions about Snape

A thread that won't sit still. Every piece of evidence cuts both ways.

## For trust

- Dumbledore's repeated, unexplained confidence in him.
- The Unbreakable Vow arguably protected Draco, not Voldemort.
- Saved a life or two, silently, more than once.

## Against

- Killed Dumbledore, in front of witnesses.
- The Half-Blood Prince's notebook leans uncomfortably dark.
- [[Hermione Granger]] agrees on the facts, not the conclusion.

## Current state

Unresolved. Likely stays that way until the [[Horcrux Hunt]] ends.`,
  },
];

const slugify = (s: string) =>
  s
    .trim()
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9\/]/g, "-")
    .replace(/-+/g, "-")
    .replace(/(^-|-$)/g, "");

function findPageBySlug(pages: SamplePage[], slug: string): SamplePage | undefined {
  const norm = slugify(slug);
  return pages.find((p) => {
    const n = slugify(p.path);
    return n === norm || n.endsWith("/" + norm) || slugify(p.title) === norm;
  });
}

type InlineNode = string | { wiki: string } | { bold: string };

function parseInline(line: string): InlineNode[] {
  const out: InlineNode[] = [];
  let i = 0;
  while (i < line.length) {
    const wikiStart = line.indexOf("[[", i);
    const boldStart = line.indexOf("**", i);
    const next =
      wikiStart === -1 ? boldStart : boldStart === -1 ? wikiStart : Math.min(wikiStart, boldStart);
    if (next === -1) {
      out.push(line.slice(i));
      break;
    }
    if (next > i) out.push(line.slice(i, next));
    if (next === wikiStart) {
      const end = line.indexOf("]]", next + 2);
      if (end === -1) {
        out.push(line.slice(i));
        break;
      }
      out.push({ wiki: line.slice(next + 2, end) });
      i = end + 2;
    } else {
      const end = line.indexOf("**", next + 2);
      if (end === -1) {
        out.push(line.slice(i));
        break;
      }
      out.push({ bold: line.slice(next + 2, end) });
      i = end + 2;
    }
  }
  return out;
}

function renderInline(
  nodes: InlineNode[],
  keyPrefix: string,
  onWikiClick: (name: string) => void,
): React.ReactNode[] {
  return nodes.map((n, i) => {
    const key = `${keyPrefix}-${i}`;
    if (typeof n === "string") return <React.Fragment key={key}>{n}</React.Fragment>;
    if ("wiki" in n)
      return (
        <a
          key={key}
          className="pensieve-wiki-link"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            onWikiClick(n.wiki);
          }}
        >
          {n.wiki}
        </a>
      );
    return <strong key={key}>{n.bold}</strong>;
  });
}

function renderMarkdown(md: string, onWikiClick: (name: string) => void): React.ReactNode {
  const lines = md.split("\n");
  const blocks: React.ReactNode[] = [];
  let i = 0;
  let keyCounter = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i++;
      continue;
    }
    if (line.startsWith("## ")) {
      blocks.push(
        <h2 key={keyCounter++}>
          {renderInline(parseInline(line.slice(3)), `h2-${keyCounter}`, onWikiClick)}
        </h2>,
      );
      i++;
    } else if (line.startsWith("# ")) {
      blocks.push(
        <h1 key={keyCounter++}>
          {renderInline(parseInline(line.slice(2)), `h1-${keyCounter}`, onWikiClick)}
        </h1>,
      );
      i++;
    } else if (line.startsWith("- ")) {
      const items: string[] = [];
      while (i < lines.length && lines[i].startsWith("- ")) {
        items.push(lines[i].slice(2));
        i++;
      }
      blocks.push(
        <ul key={keyCounter++}>
          {items.map((it, j) => (
            <li key={j}>{renderInline(parseInline(it), `li-${keyCounter}-${j}`, onWikiClick)}</li>
          ))}
        </ul>,
      );
    } else {
      const paraLines: string[] = [line];
      i++;
      while (
        i < lines.length &&
        lines[i].trim() &&
        !lines[i].startsWith("#") &&
        !lines[i].startsWith("- ")
      ) {
        paraLines.push(lines[i]);
        i++;
      }
      const text = paraLines.join(" ");
      blocks.push(
        <p key={keyCounter++}>
          {renderInline(parseInline(text), `p-${keyCounter}`, onWikiClick)}
        </p>,
      );
    }
  }
  return blocks;
}

type Props = {
  onBack: () => void;
  onContinue: () => void;
};

export function PensieveStep({ onBack, onContinue }: Props) {
  const [selectedPath, setSelectedPath] = useState<string | null>(null);

  const grouped = useMemo(() => {
    const map = new Map<string, SamplePage[]>();
    for (const p of SAMPLE_PAGES) {
      const list = map.get(p.category) || [];
      list.push(p);
      map.set(p.category, list);
    }
    return Array.from(map.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, []);

  const selected = SAMPLE_PAGES.find((p) => p.path === selectedPath);

  const handleWikiClick = (name: string) => {
    const target = findPageBySlug(SAMPLE_PAGES, name);
    if (target) setSelectedPath(target.path);
  };

  if (selected) {
    return (
      <div className="page active" style={{ maxWidth: 480 }}>
        <div className="pensieve-onboarding-detail">
          <button
            className="pensieve-back-btn"
            onClick={() => setSelectedPath(null)}
            type="button"
          >
            <svg width="12" height="12" viewBox="0 0 14 14" fill="none">
              <path d="M9 2L4 7l5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            All pages
          </button>
          <div className="pensieve-onboarding-detail-header">
            <span className="pensieve-onboarding-detail-title">{selected.title}</span>
            <span
              className="pensieve-confidence pensieve-confidence--sm"
              style={{
                background: `${confidenceColor(selected.confidence)}18`,
                color: confidenceColor(selected.confidence),
              }}
            >
              {(selected.confidence * 100).toFixed(0)}% {confidenceLabel(selected.confidence)}
            </span>
          </div>
          <div className="pensieve-onboarding-content">
            {renderMarkdown(selected.markdown, handleWikiClick)}
          </div>
        </div>
        <div className="btn-row">
          <button className="btn btn-ghost" onClick={onBack}>Back</button>
          <button className="btn btn-primary" onClick={onContinue}>Finish Setup</button>
        </div>
      </div>
    );
  }

  return (
    <div className="page active" style={{ maxWidth: 480 }}>
      <div className="page-icon">
        <svg width="22" height="22" viewBox="0 0 16 16" fill="none">
          <path d="M3 2h7l3 3v9H3V2z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round"/>
          <path d="M10 2v3h3" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round"/>
          <path d="M5 8h6M5 10.5h6M5 13h4" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round"/>
        </svg>
      </div>
      <div className="page-title">Pensieve</div>
      <p className="page-desc">
        A wiki of your life, written automatically as you go — like the Pensieve in Harry Potter. Pages for the people, projects, and threads that keep coming up, linked so you can step back into any of them.
      </p>

      <div className="pensieve-onboarding-list">
        {grouped.map(([category, pages]) => (
          <div key={category} className="pensieve-category-group">
            <h3 className="pensieve-category-label">{category}</h3>
            <div className="pensieve-onboarding-grid">
              {pages.map((page) => (
                <section
                  key={page.path}
                  className="pensieve-page-card"
                  onClick={() => setSelectedPath(page.path)}
                >
                  <div className="pensieve-card-header">
                    <h4 className="pensieve-card-title">{page.title}</h4>
                    <span
                      className="pensieve-confidence pensieve-confidence--sm"
                      style={{
                        background: `${confidenceColor(page.confidence)}18`,
                        color: confidenceColor(page.confidence),
                      }}
                    >
                      {(page.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                  <div className="pensieve-card-meta">{page.last_updated}</div>
                </section>
              ))}
            </div>
          </div>
        ))}
      </div>

      <p className="tadas-hint">
        Pages are auto-generated from what you do. Click to open; [[wiki-links]] jump between them — edit any time.
      </p>

      <div className="btn-row">
        <button className="btn btn-ghost" onClick={onBack}>Back</button>
        <button className="btn btn-primary" onClick={onContinue}>Finish Setup</button>
      </div>
    </div>
  );
}
