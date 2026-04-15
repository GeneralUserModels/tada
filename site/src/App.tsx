import React, { useEffect, useRef, useState } from "react";
import { DEMOS } from "./demos";

const REPO = "GeneralUserModels/tada";
const RELEASE_URL = `https://github.com/${REPO}/releases/latest`;

const SPINNER_FRAMES = ["◐", "◓", "◑", "◒"];

interface Segment {
  source: "user" | "assistant";
  text: string;
}

interface SelectionState {
  count: number;
  from: "start" | "end" | "middle";
  start?: number;
}

function useAutocompleteDemo() {
  const [demoIdx, setDemoIdx] = useState(0);
  const [segments, setSegments] = useState<Segment[]>([]);
  const [selection, setSelection] = useState<SelectionState | null>(null);
  const [spinnerIdx, setSpinnerIdx] = useState(0);
  const [spinnerPct, setSpinnerPct] = useState(0);
  const [showSpinner, setShowSpinner] = useState(false);
  const [showTabHint, setShowTabHint] = useState(false);
  const [running, setRunning] = useState(true);
  const segmentsRef = useRef<Segment[]>([]);

  const demo = DEMOS[demoIdx];

  useEffect(() => {
    let cancelled = false;

    function sleep(ms: number) {
      return new Promise<void>((resolve) => {
        window.setTimeout(resolve, ms);
      });
    }

    function delayForUserChar(char: string) {
      const isPunctuation = /[,.!?;:]/.test(char);
      const isWhitespace = char === " ";
      const isNewline = char === "\n";

      let base = 18;
      if (isWhitespace) base = 11;
      if (isPunctuation) base += 46;
      if (isNewline) base += 78;
      return base + Math.floor(Math.random() * 12);
    }

    function delayForAssistantToken(token: string) {
      const isWhitespace = /^\s+$/.test(token);
      const hasNewline = token.includes("\n");
      const endsWithPunctuation = /[,.!?;:]$/.test(token.trim());
      const wordLength = token.trim().length;

      let base = 44;
      if (isWhitespace) base = hasNewline ? 40 : 20;
      if (!isWhitespace) base += Math.min(wordLength * 2, 12);
      if (endsWithPunctuation) base += 24;
      if (hasNewline) base += 18;
      return base + Math.floor(Math.random() * 10);
    }

    function appendText(source: Segment["source"], text: string) {
      setSegments((prev) => {
        if (prev.length === 0) {
          const next = [{ source, text }];
          segmentsRef.current = next;
          return next;
        }
        const next = [...prev];
        const last = next[next.length - 1];
        if (last.source === source) {
          next[next.length - 1] = { ...last, text: last.text + text };
          segmentsRef.current = next;
          return next;
        }
        next.push({ source, text });
        segmentsRef.current = next;
        return next;
      });
    }

    function deleteChars(
      count: number,
      from: "start" | "end" | "middle",
      start = 0
    ) {
      setSegments((prev) => {
        if (prev.length === 0 || count <= 0) return prev;
        const next = [...prev];
        let remaining = count;

        if (from === "start") {
          while (remaining > 0 && next.length > 0) {
            const first = next[0];
            if (first.text.length <= remaining) {
              remaining -= first.text.length;
              next.shift();
              continue;
            }
            next[0] = { ...first, text: first.text.slice(remaining) };
            remaining = 0;
          }
          segmentsRef.current = next;
          return next;
        }

        if (from === "middle") {
          const totalChars = next.reduce(
            (sum, segment) => sum + segment.text.length,
            0
          );
          const removeStart = Math.max(0, Math.min(start, totalChars));
          const removeEnd = Math.max(
            removeStart,
            Math.min(removeStart + count, totalChars)
          );

          let cursor = 0;
          const rebuilt: Segment[] = [];
          for (const segment of next) {
            const segStart = cursor;
            const segEnd = segStart + segment.text.length;
            cursor = segEnd;

            if (segEnd <= removeStart || segStart >= removeEnd) {
              rebuilt.push(segment);
              continue;
            }

            const keepPrefixLen = Math.max(0, removeStart - segStart);
            const keepSuffixStart = Math.max(0, removeEnd - segStart);
            const prefix = segment.text.slice(0, keepPrefixLen);
            const suffix = segment.text.slice(keepSuffixStart);

            if (prefix) rebuilt.push({ source: segment.source, text: prefix });
            if (suffix) rebuilt.push({ source: segment.source, text: suffix });
          }

          const merged: Segment[] = [];
          for (const segment of rebuilt) {
            const last = merged[merged.length - 1];
            if (last && last.source === segment.source) {
              last.text += segment.text;
            } else {
              merged.push({ ...segment });
            }
          }

          segmentsRef.current = merged;
          return merged;
        }

        while (remaining > 0 && next.length > 0) {
          const lastIdx = next.length - 1;
          const last = next[lastIdx];
          if (last.text.length <= remaining) {
            remaining -= last.text.length;
            next.pop();
            continue;
          }
          next[lastIdx] = { ...last, text: last.text.slice(0, -remaining) };
          remaining = 0;
        }
        segmentsRef.current = next;
        return next;
      });
    }

    async function runDemo() {
      setSegments([]);
      segmentsRef.current = [];
      setSpinnerIdx(0);
      setSpinnerPct(0);
      setShowSpinner(false);
      setShowTabHint(false);
      setSelection(null);
      setRunning(true);

      for (const [stepIdx, step] of demo.steps.entries()) {
        if (cancelled) return;

        if (step.kind === "delete") {
          await sleep(360 + Math.floor(Math.random() * 260));
          let from = step.from ?? "end";
          let count = step.count ?? 0;
          let start = step.start ?? 0;

          if (step.matchText) {
            const fullText = segmentsRef.current
              .map((segment) => segment.text)
              .join("");
            const idx = fullText.indexOf(step.matchText);
            if (idx >= 0) {
              from = "middle";
              start = idx;
              if (count <= 0) count = step.matchText.length;
            }
          }

          if (count <= 0) {
            await sleep(step.pauseAfter ?? 620);
            continue;
          }

          setSelection({ count, from, start });
          await sleep(360 + Math.floor(Math.random() * 260));
          if (cancelled) return;
          deleteChars(count, from, start);
          setSelection(null);
          await sleep(step.pauseAfter ?? 620);
          continue;
        }

        if (step.kind === "assistant") {
          setShowSpinner(true);
          setShowTabHint(step.trigger === "autocomplete");

          const totalTicks = 6 + Math.floor(Math.random() * 4);
          for (let tick = 0; tick < totalTicks; tick++) {
            if (cancelled) return;
            setSpinnerIdx(tick % SPINNER_FRAMES.length);
            setSpinnerPct(Math.round(((tick + 1) / totalTicks) * 100));
            await sleep(65 + Math.floor(Math.random() * 30));
          }

          setShowSpinner(false);
          setShowTabHint(false);
        }

        const source: Segment["source"] =
          step.kind === "user" ? "user" : "assistant";
        let textToType = step.text;
        if (step.kind === "user") {
          const normalizedUserText = step.text.replace(/^\n+/, "");
          if (stepIdx === 0) {
            textToType = normalizedUserText;
          } else {
            const lastSegment = segmentsRef.current[segmentsRef.current.length - 1];
            const trailingNewlineCount =
              lastSegment?.text.match(/\n*$/)?.[0].length ?? 0;
            const separatorNewlines = Math.max(0, 2 - trailingNewlineCount);
            textToType = `${"\n".repeat(separatorNewlines)}${normalizedUserText}`;
          }
        }

        if (source === "user") {
          for (const char of textToType) {
            if (cancelled) return;
            appendText(source, char);
            await sleep(delayForUserChar(char));
          }
        } else {
          const tokens = textToType.match(/(\s+|[^\s]+)/g) ?? [];
          for (const token of tokens) {
            if (cancelled) return;
            appendText(source, token);
            await sleep(delayForAssistantToken(token));
          }
        }

        await sleep(step.pauseAfter ?? 500);
      }

      const finalArtifactText =
        [...segmentsRef.current]
          .reverse()
          .find((segment) => segment.source === "assistant" && segment.text.length > 0)
          ?.text ?? "";
      const totalChars = segmentsRef.current.reduce(
        (sum, segment) => sum + segment.text.length,
        0
      );
      const charsToDelete = Math.max(0, totalChars - finalArtifactText.length);

      if (charsToDelete > 0) {
        setSelection({ count: charsToDelete, from: "start" });
        await sleep(420 + Math.floor(Math.random() * 260));
        if (cancelled) return;
        deleteChars(charsToDelete, "start");
        setSelection(null);
      }

      setRunning(false);
      await sleep(3600);
      if (!cancelled) {
        setDemoIdx((idx) => (idx + 1) % DEMOS.length);
      }
    }

    runDemo();

    return () => {
      cancelled = true;
    };
  }, [demo]);

  const spinnerText =
    showSpinner
      ? `${SPINNER_FRAMES[spinnerIdx]} ${spinnerPct.toString().padStart(3, " ")}%`
      : "";

  return {
    demoIdx,
    segments,
    selection,
    spinnerText,
    showSpinner,
    showTabHint,
    running,
  };
}

export function App() {
  const {
    demoIdx,
    segments,
    selection,
    spinnerText,
    showSpinner,
    showTabHint,
    running,
  } = useAutocompleteDemo();
  const demoBodyRef = useRef<HTMLDivElement>(null);

  const demo = DEMOS[demoIdx];
  const theme = demo.theme;

  const demoStyle = {
    "--demo-bg": theme.bg,
    "--demo-header-bg": theme.headerBg,
    "--demo-header-text": theme.headerText,
    "--demo-text": theme.textColor,
    "--demo-cursor": theme.cursorColor,
    "--demo-font": theme.fontFamily,
    "--demo-font-size": theme.fontSize,
  } as React.CSSProperties;

  const selectedRanges: Array<{ start: number; end: number } | null> = new Array(
    segments.length
  ).fill(null);

  if (selection) {
    const totalChars = segments.reduce((sum, segment) => sum + segment.text.length, 0);
    const baseStart =
      selection.from === "start"
        ? 0
        : selection.from === "end"
          ? Math.max(0, totalChars - selection.count)
          : Math.max(0, Math.min(selection.start ?? 0, totalChars));
    const selectionStart = Math.min(baseStart, totalChars);
    const selectionEnd = Math.min(totalChars, selectionStart + selection.count);

    let cursor = 0;
    for (let idx = 0; idx < segments.length; idx++) {
      const segment = segments[idx];
      const segStart = cursor;
      const segEnd = segStart + segment.text.length;
      cursor = segEnd;

      const overlapStart = Math.max(segStart, selectionStart);
      const overlapEnd = Math.min(segEnd, selectionEnd);
      if (overlapEnd > overlapStart) {
        selectedRanges[idx] = {
          start: overlapStart - segStart,
          end: overlapEnd - segStart,
        };
      }
    }
  }

  useEffect(() => {
    const node = demoBodyRef.current;
    if (!node) return;
    const centeredScrollTop = Math.max(
      0,
      node.scrollHeight - node.clientHeight * 0.5
    );
    node.scrollTop = centeredScrollTop;
  }, [demoIdx, segments, selection, showSpinner]);

  return (
    <div className="page">
      <div className="grain" />

      <main className="hero">
        <h1 className="hero-title">
          Tabracadabra{" "}
          <span className="hero-emoji" aria-hidden="true">
            🎩
          </span>
        </h1>
        <p className="hero-subtitle">
          An intelligent, context-aware assistant, in every textbox.
        </p>

        <div className="hero-actions">
          <a href={RELEASE_URL} className="btn btn-primary">
            <DownloadIcon />
            Download for macOS
          </a>
          <a href={`https://github.com/${REPO}`} className="btn btn-secondary">
            <StarIcon />
            Star on GitHub
          </a>
        </div>
      </main>

      <div className="demo-container">
        <div className="demo" style={demoStyle}>
          <div className="demo-header">
            <div className="demo-dots">
              <span />
              <span />
              <span />
            </div>
            <div className="demo-app-label">
              <span className="demo-app-icon">{theme.icon}</span>
              {theme.app}
            </div>
            <div className="demo-tab-hint">
              {showSpinner && showTabHint && (
                <span className="tab-key-badge">
                  Option + Tab
                </span>
              )}
            </div>
          </div>

          {demo.topChrome}

          <div ref={demoBodyRef} className="demo-body">
            {segments.map((segment, idx) => (
              (() => {
                const className =
                  segment.source === "user" ? "demo-typed" : "demo-completion";
                const selectedRange = selectedRanges[idx];

                if (!selectedRange) {
                  return (
                    <span key={`${idx}-${segment.source}`} className={className}>
                      {segment.text}
                    </span>
                  );
                }

                const leadingText = segment.text.slice(0, selectedRange.start);
                const selectedText = segment.text.slice(
                  selectedRange.start,
                  selectedRange.end
                );
                const trailingText = segment.text.slice(selectedRange.end);

                return (
                  <React.Fragment key={`${idx}-${segment.source}`}>
                    {leadingText && <span className={className}>{leadingText}</span>}
                    <span className="demo-selection">{selectedText}</span>
                    {trailingText && <span className={className}>{trailingText}</span>}
                  </React.Fragment>
                );
              })()
            ))}
            {showSpinner && (
              <span className="demo-spinner">{spinnerText}</span>
            )}
            {running && <span className="demo-cursor" />}
            <span className="demo-scroll-spacer" aria-hidden="true" />
          </div>

          {demo.bottomChrome}
        </div>
      </div>

    </div>
  );
}

function StarIcon() {
  return (
    <svg
      width="15"
      height="15"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
    </svg>
  );
}

function DownloadIcon() {
  return (
    <svg
      width="15"
      height="15"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="7 10 12 15 17 10" />
      <line x1="12" y1="15" x2="12" y2="3" />
    </svg>
  );
}
