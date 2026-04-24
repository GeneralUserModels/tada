import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  LABELS,
  WIKI_PAGES,
  type RawEvent,
  type Source,
  type WikiPage,
} from "./data";
import {
  labelTypedText,
  showcaseProgress,
  useTimelineDriver,
  type DemoState,
} from "./driver";
import "./memex.css";

const GH_REPO = "GeneralUserModels/tada";
const GH_URL = `https://github.com/${GH_REPO}`;
const RELEASES_PAGE = `${GH_URL}/releases/latest`;

function useDmgUrl(): string {
  const [url, setUrl] = useState(RELEASES_PAGE);
  useEffect(() => {
    fetch(`https://api.github.com/repos/${GH_REPO}/releases`, {
      headers: { Accept: "application/vnd.github.v3+json" },
    })
      .then((res) => (res.ok ? res.json() : Promise.reject()))
      .then(
        (
          releases: Array<{
            assets: Array<{ name: string; browser_download_url: string }>;
          }>
        ) => {
          for (const release of releases) {
            const dmg = release.assets.find(
              (a) => a.name.endsWith(".dmg") && a.name.includes("arm64")
            );
            if (dmg) {
              setUrl(dmg.browser_download_url);
              return;
            }
          }
        }
      )
      .catch(() => {});
  }, []);
  return url;
}

const SOURCE_META: Record<
  Source,
  { name: string; glyph: string }
> = {
  screen:   { name: "screen",       glyph: "◱" },
  email:    { name: "email",        glyph: "✉" },
  calendar: { name: "calendar",     glyph: "▦" },
  notif:    { name: "notifications",glyph: "◉" },
  filesys:  { name: "filesystem",   glyph: "≡" },
};

const SOURCE_ORDER: Source[] = ["screen", "email", "calendar", "notif", "filesys"];

// ─────────────────────────────────────────────────────────────
// Root
// ─────────────────────────────────────────────────────────────

export function MemexDemo() {
  const [interactive, setInteractive] = useState(false);
  const [selectedSlug, setSelectedSlug] = useState<string>("people/scarecrow");
  const state = useTimelineDriver(interactive, selectedSlug);
  const dmgUrl = useDmgUrl();

  const openPage = useCallback((slug: string) => {
    if (!WIKI_PAGES[slug]) return;
    setSelectedSlug(slug);
    setInteractive(true);
  }, []);

  // When the timeline reaches its end, the driver emits `browseRequested`.
  // Flip interactive mode on so the demo settles into the browsable wiki
  // instead of looping back to an empty start.
  useEffect(() => {
    if (state.browseRequested && !interactive) setInteractive(true);
  }, [state.browseRequested, interactive]);

  return (
    <div className="memex-root">
      <div className="memex-grain" aria-hidden="true" />

      <MemexHero
        dmgUrl={dmgUrl}
        interactive={interactive}
        onBrowse={() => setInteractive(true)}
        onExit={() => setInteractive(false)}
      />

      <div
        className="memex-stage"
        data-phase={interactive ? "browse" : state.phase}
        data-interactive={interactive || undefined}
      >
        <div className="memex-canvas">
          <Titlebar
            elapsed={state.elapsed}
            phase={state.phase}
            interactive={interactive}
          />
          <div className="memex-body">
            <LeftPanel state={state} onLinkClick={openPage} />
            <RightPanel
              state={state}
              interactive={interactive}
              onSelect={openPage}
            />
          </div>
          {state.phase === "twister" && !interactive && <TwisterOverlay />}
        </div>
      </div>

      <MemexFooter />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// Hero
// ─────────────────────────────────────────────────────────────

function MemexHero({
  dmgUrl,
  interactive,
  onBrowse,
  onExit,
}: {
  dmgUrl: string;
  interactive: boolean;
  onBrowse: () => void;
  onExit: () => void;
}) {
  return (
    <header className="memex-hero">
      <h1 className="memex-hero-title">
        <MemexLogo />
        Memex
      </h1>
      <p className="memex-hero-subtitle">
        A wiki of your memories, built passively.
      </p>
      <div className="memex-hero-actions">
        <a className="memex-btn memex-btn-primary" href={dmgUrl}>
          <DownloadIcon />
          <span>Download for macOS</span>
          <span className="memex-btn-sub">(Apple Silicon)</span>
        </a>
        <a
          className="memex-btn memex-btn-secondary"
          href={GH_URL}
          target="_blank"
          rel="noreferrer"
        >
          <StarIcon />
          <span>Star on GitHub</span>
        </a>
        {interactive ? (
          <button
            className="memex-btn memex-btn-ghost"
            onClick={onExit}
            type="button"
          >
            <span>← Back to the demo</span>
          </button>
        ) : (
          <button
            className="memex-btn memex-btn-accent"
            onClick={onBrowse}
            type="button"
          >
            <CursorIcon />
            <span>Browse Dorothy's memex</span>
          </button>
        )}
      </div>
    </header>
  );
}

function MemexFooter() {
  return (
    <footer className="memex-footer">
      <a href={GH_URL} target="_blank" rel="noreferrer">
        github.com/{GH_REPO}
      </a>
      <span>·</span>
      <span>tada</span>
    </footer>
  );
}

function MemexLogo() {
  // Pulled from src/client/renderer/components/Sidebar.tsx (the sidebar nav icon).
  return (
    <svg
      className="memex-hero-logo"
      viewBox="0 0 16 16"
      fill="none"
      aria-hidden="true"
    >
      <circle cx="8"    cy="3.5" r="1.5" stroke="currentColor" strokeWidth="1.3" />
      <circle cx="3.5"  cy="8"   r="1.5" stroke="currentColor" strokeWidth="1.3" />
      <circle cx="12.5" cy="8"   r="1.5" stroke="currentColor" strokeWidth="1.3" />
      <circle cx="5.5"  cy="13"  r="1.5" stroke="currentColor" strokeWidth="1.3" />
      <circle cx="10.5" cy="13"  r="1.5" stroke="currentColor" strokeWidth="1.3" />
      <path
        d="M6.5 4.5L5 6.5M9.5 4.5L11 6.5M3.5 9.5L5 11.5M12.5 9.5L11 11.5"
        stroke="currentColor"
        strokeWidth="1.1"
        strokeLinecap="round"
      />
    </svg>
  );
}

function DownloadIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="7 10 12 15 17 10" />
      <line x1="12" y1="15" x2="12" y2="3" />
    </svg>
  );
}

function StarIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
    </svg>
  );
}

function CursorIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M4 4l16 6-7 3-3 7z" />
    </svg>
  );
}

// ─────────────────────────────────────────────────────────────
// Titlebar
// ─────────────────────────────────────────────────────────────

function Titlebar({
  elapsed,
  phase,
  interactive,
}: {
  elapsed: number;
  phase: string;
  interactive: boolean;
}) {
  const label = interactive
    ? "browsing"
    : phase === "ingest"
      ? "watching"
      : phase === "twister"
        ? "compiling"
        : phase === "wiki"
          ? "indexed"
          : "";
  return (
    <div className="memex-titlebar">
      <div className="memex-dots">
        <span /><span /><span />
      </div>
      <div className="memex-titlebar-label">
        <span className="memex-icon" aria-hidden>◈</span>
        <span className="memex-app">Dorothy's memex</span>
        <span className="memex-path-sep">·</span>
        <span className="memex-path">~/logs/memory/</span>
      </div>
      <div className="memex-titlebar-right">
        <span className="memex-status">{label}</span>
        {!interactive && (
          <span className="memex-timecode">{formatTimecode(elapsed)}</span>
        )}
      </div>
    </div>
  );
}

function formatTimecode(elapsed: number): string {
  const secs = Math.floor(elapsed / 1000);
  const mm = String(Math.floor(secs / 60)).padStart(2, "0");
  const ss = String(secs % 60).padStart(2, "0");
  return `t+${mm}:${ss}`;
}

// ─────────────────────────────────────────────────────────────
// Title overlay (first 2.5s)
// ─────────────────────────────────────────────────────────────

// ─────────────────────────────────────────────────────────────
// Left panel — source lanes + label synth
// ─────────────────────────────────────────────────────────────

function LeftPanel({
  state,
  onLinkClick,
}: {
  state: DemoState;
  onLinkClick: (slug: string) => void;
}) {
  const active = labelTypedText(state.activeLabel, state.elapsed);
  const activeLabelMeta = state.activeLabel
    ? LABELS.find((l) => l.id === state.activeLabel!.id) ?? null
    : null;

  return (
    <div className="memex-left">
      <div className="memex-lanes">
        {SOURCE_ORDER.map((src) => (
          <SourceLane
            key={src}
            source={src}
            events={state.rawEventsBySource[src] ?? []}
          />
        ))}
      </div>
      <div className="memex-label-synth">
        <div className="memex-label-synth-header">
          <span className="synth-dot" />
          <span className="synth-model">Passive labeling</span>
          <span className="synth-sep">·</span>
          <span className="synth-label">
            describing each observed action, in natural language
          </span>
        </div>
        <div className="memex-label-synth-body">
          {active ? (
            <>
              <span className="synth-text">{active.text}</span>
              {!active.done && <span className="synth-cursor" />}
            </>
          ) : (
            <span className="synth-placeholder">waiting for signal…</span>
          )}
        </div>
        <div className="memex-label-synth-target">
          {activeLabelMeta?.pages.map((slug) => (
            <WikilinkChip key={slug} slug={slug} small onClick={onLinkClick} />
          ))}
        </div>
      </div>
    </div>
  );
}

function WikilinkChip({
  slug,
  small,
  onClick,
}: {
  slug: string;
  small?: boolean;
  onClick: (slug: string) => void;
}) {
  return (
    <button
      type="button"
      className={`wikilink${small ? " wikilink-sm" : ""}`}
      onClick={() => onClick(slug)}
    >
      [[{slug}]]
    </button>
  );
}

function SourceLane({ source, events }: { source: Source; events: RawEvent[] }) {
  const meta = SOURCE_META[source];
  return (
    <div className="lane" data-source={source}>
      <div className="lane-header">
        <span className="lane-glyph">{meta.glyph}</span>
        <span className="lane-name">{meta.name}</span>
        <span className="lane-count">{events.length}</span>
      </div>
      <div className="lane-chips">
        {events.length === 0 && <div className="lane-empty">—</div>}
        {events.map((e, idx) => (
          <div className="lane-chip" key={e.id} data-idx={idx}>
            <span className="chip-ts">{e.ts}</span>
            <span className="chip-text">{e.text}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// Right panel — wiki
// ─────────────────────────────────────────────────────────────

function RightPanel({
  state,
  interactive,
  onSelect,
}: {
  state: DemoState;
  interactive: boolean;
  onSelect: (slug: string) => void;
}) {
  return (
    <div className="memex-right">
      <div className="memex-right-header">
        <span className="panel-eyebrow">memex · ~/logs/memory/</span>
      </div>
      <WikiView state={state} interactive={interactive} onSelect={onSelect} />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// Wiki view
// ─────────────────────────────────────────────────────────────

function WikiView({
  state,
  interactive,
  onSelect,
}: {
  state: DemoState;
  interactive: boolean;
  onSelect: (slug: string) => void;
}) {
  const showcased = state.showcasedSlug ? WIKI_PAGES[state.showcasedSlug] : null;
  return (
    <div className="wiki-view">
      <FileTree
        createdPages={state.createdPages}
        showcasedSlug={state.showcasedSlug}
        interactive={interactive}
        onSelect={onSelect}
      />
      <div className="wiki-page-pane">
        {showcased ? (
          <ShowcasedPage
            key={showcased.slug}
            page={showcased}
            state={state}
            interactive={interactive}
            onLinkClick={onSelect}
          />
        ) : (
          <WikiIdlePlaceholder count={state.createdPages.length} />
        )}
      </div>
    </div>
  );
}

function WikiIdlePlaceholder({ count }: { count: number }) {
  return (
    <div className="wiki-idle">
      <div className="wiki-idle-title">memex</div>
      <div className="wiki-idle-sub">
        {count === 0
          ? "no pages yet — waiting for labels"
          : `${count} page${count === 1 ? "" : "s"} indexed`}
      </div>
    </div>
  );
}

function FileTree({
  createdPages,
  showcasedSlug,
  interactive,
  onSelect,
}: {
  createdPages: string[];
  showcasedSlug: string | null;
  interactive: boolean;
  onSelect: (slug: string) => void;
}) {
  const byDir = useMemo(() => {
    const out: Record<string, string[]> = {
      people: [],
      projects: [],
      interests: [],
      work: [],
    };
    for (const slug of createdPages) {
      const page = WIKI_PAGES[slug];
      if (!page) continue;
      (out[page.dir] ??= []).push(slug);
    }
    return out;
  }, [createdPages]);

  const dirs: Array<"people" | "projects" | "interests" | "work"> = [
    "people",
    "projects",
    "interests",
    "work",
  ];

  return (
    <div className="file-tree">
      {dirs.map((dir) => {
        const pages = byDir[dir] ?? [];
        if (pages.length === 0) return null;
        return (
          <div key={dir} className="ft-dir">
            <div className="ft-dir-header">
              <span className="ft-icon">📂</span>
              <span className="ft-dir-name">{dir}/</span>
              <span className="ft-dir-count">{pages.length}</span>
            </div>
            <div className="ft-files">
              {pages.map((slug) => {
                const page = WIKI_PAGES[slug];
                const name = slug.slice(dir.length + 1) + ".md";
                const active = slug === showcasedSlug;
                const className = `ft-file${active ? " ft-file-active" : ""}${interactive ? " ft-file-clickable" : ""}`;
                const inner = (
                  <>
                    <span className="ft-file-name">{name}</span>
                    <span className="ft-file-conf">
                      {page.confidenceEnd.toFixed(2)}
                    </span>
                  </>
                );
                return interactive ? (
                  <button
                    key={slug}
                    type="button"
                    className={className}
                    title={slug}
                    onClick={() => onSelect(slug)}
                  >
                    {inner}
                  </button>
                ) : (
                  <div key={slug} className={className} title={slug}>
                    {inner}
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// Showcased page
// ─────────────────────────────────────────────────────────────

function ShowcasedPage({
  page,
  state,
  interactive,
  onLinkClick,
}: {
  page: WikiPage;
  state: DemoState;
  interactive: boolean;
  onLinkClick: (slug: string) => void;
}) {
  const prog = interactive ? 1 : showcaseProgress(state);
  const currentConfidence =
    page.confidenceStart + (page.confidenceEnd - page.confidenceStart) * prog;

  // Progressive reveal schedule (fraction of showcase progress).
  const ledeVisible = prog > 0.06;
  const body0Visible = prog > 0.22;
  const body1Visible = prog > 0.45;

  // Typing progress for lede: characters proportional to (prog - 0.06) up to 0.22
  const ledeFrac = clamp01((prog - 0.06) / 0.16);
  const body0Frac = clamp01((prog - 0.22) / 0.22);
  const body1Frac = clamp01((prog - 0.45) / 0.22);

  const ledeShown = page.lede.slice(0, Math.floor(page.lede.length * ledeFrac));
  const body0 = page.body.find((b) => b.kind === "p");
  const body1 = page.body.filter((b) => b.kind === "p")[1];
  const updatedBlock = page.body.find((b) => b.kind === "updated");
  const unknownBlock = page.body.find((b) => b.kind === "unknown");

  const confClass = confidenceBucket(currentConfidence);

  return (
    <div className="wiki-page">
      <div className="wiki-path-bar">
        <span className="wiki-path-crumb">{page.dir}</span>
        <span className="wiki-path-sep">/</span>
        <span className="wiki-path-leaf">{page.slug.split("/").pop()}.md</span>
      </div>

      <div className="wiki-title-row">
        <h1 className="wiki-h1">{page.title}</h1>
        <span className={`wiki-confidence wiki-confidence-${confClass}`}>
          <span className="wiki-confidence-num">
            {currentConfidence.toFixed(2)}
          </span>
          <span className="wiki-confidence-label">
            {confidenceLabel(currentConfidence)}
          </span>
        </span>
      </div>

      <div className="wiki-meta">
        <span>last updated {page.lastUpdated}</span>
      </div>

      {ledeVisible && (
        <p className="wiki-lede">
          <WithWikilinks text={ledeShown} onClick={onLinkClick} />
          {ledeFrac < 1 && <span className="wiki-cursor" />}
        </p>
      )}

      {body0Visible && body0 && body0.kind === "p" && (
        <p className="wiki-p">
          <WithWikilinks
            text={body0.text.slice(0, Math.floor(body0.text.length * body0Frac))}
            onClick={onLinkClick}
          />
          {body0Frac < 1 && <span className="wiki-cursor" />}
        </p>
      )}

      {body1Visible && body1 && body1.kind === "p" && (
        <p className="wiki-p">
          <WithWikilinks
            text={body1.text.slice(0, Math.floor(body1.text.length * body1Frac))}
            onClick={onLinkClick}
          />
          {body1Frac < 1 && <span className="wiki-cursor" />}
        </p>
      )}

      {state.showUpdated && updatedBlock && updatedBlock.kind === "updated" && (
        <div className="wiki-updated">
          <div className="wiki-updated-header">
            <span className="wiki-updated-badge">[!updated]</span>
            <span className="wiki-updated-date">{updatedBlock.date}</span>
          </div>
          <div className="wiki-updated-body">
            <WithWikilinks text={updatedBlock.text} onClick={onLinkClick} />
          </div>
        </div>
      )}

      {state.showUnknown && unknownBlock && unknownBlock.kind === "unknown" && (
        <div className="wiki-unknown">
          <h2 className="wiki-h2">What We Don't Know</h2>
          <ul className="wiki-unknown-list">
            {unknownBlock.items.map((it, i) => (
              <li key={i}>{it}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function clamp01(x: number): number {
  return Math.max(0, Math.min(1, x));
}

// Mirror of confidenceLabel buckets in src/client/renderer/components/views/memexHelpers.ts
function confidenceBucket(c: number): "low" | "mid" | "high" | "max" {
  if (c < 0.3) return "low";
  if (c < 0.6) return "mid";
  if (c < 0.8) return "high";
  return "max";
}

function confidenceLabel(c: number): string {
  if (c < 0.3) return "speculative";
  if (c < 0.6) return "probable";
  if (c < 0.8) return "confident";
  return "certain";
}

// Render [[slug]] tokens as highlighted wikilinks. Always clickable — a click
// switches the demo into interactive Browse mode and opens the linked page.
function WithWikilinks({
  text,
  onClick,
}: {
  text: string;
  onClick?: (slug: string) => void;
}) {
  const parts = splitWikilinks(text);
  return (
    <>
      {parts.map((part, i) =>
        part.kind === "text" ? (
          <React.Fragment key={i}>{part.text}</React.Fragment>
        ) : onClick ? (
          <button
            key={i}
            type="button"
            className="wikilink wikilink-inline"
            onClick={() => onClick(part.slug)}
          >
            [[{part.slug}]]
          </button>
        ) : (
          <span key={i} className="wikilink wikilink-inline">
            [[{part.slug}]]
          </span>
        )
      )}
    </>
  );
}

type WikilinkPart =
  | { kind: "text"; text: string }
  | { kind: "link"; slug: string };

function splitWikilinks(text: string): WikilinkPart[] {
  const out: WikilinkPart[] = [];
  const re = /\[\[([^\]]+)\]\]/g;
  let lastIdx = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) != null) {
    if (m.index > lastIdx) {
      out.push({ kind: "text", text: text.slice(lastIdx, m.index) });
    }
    out.push({ kind: "link", slug: m[1] });
    lastIdx = m.index + m[0].length;
  }
  if (lastIdx < text.length) {
    out.push({ kind: "text", text: text.slice(lastIdx) });
  }
  return out;
}

// ─────────────────────────────────────────────────────────────
// Twister transition overlay
// ─────────────────────────────────────────────────────────────

function TwisterOverlay() {
  return (
    <div className="twister-overlay">
      <div className="twister-ring twister-ring-1" />
      <div className="twister-ring twister-ring-2" />
      <div className="twister-ring twister-ring-3" />
      <div className="twister-caption">compiling…</div>
    </div>
  );
}

