import { useState, useRef, useEffect } from "react";

export interface ModelOption {
  value: string;
  label: string;
}

export const LLM_MODELS: ModelOption[] = [
  { value: "anthropic/claude-haiku-4-5-20251001", label: "Claude Haiku 4.5" },
  { value: "anthropic/claude-sonnet-4-6",         label: "Claude Sonnet 4.6" },
  { value: "anthropic/claude-opus-4-6",           label: "Claude Opus 4.6" },
  { value: "gemini/gemini-3-flash-preview",       label: "Gemini Flash 3.0 Preview" },
];

export const TINKER_MODELS: ModelOption[] = [
  { value: "Qwen/Qwen3-VL-30B-A3B-Instruct", label: "Qwen3-VL-30B-A3B" },
];

interface Props {
  value: string;
  onChange: (value: string) => void;
  options: ModelOption[];
  placeholder?: string;
}

export function ModelDropdown({ value, onChange, options, placeholder = "Select a model" }: Props) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [highlightedIndex, setHighlightedIndex] = useState(-1);
  const ref = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const itemRefs = useRef<(HTMLButtonElement | null)[]>([]);

  const filtered = options.filter(o =>
    o.label.toLowerCase().includes(search.toLowerCase()) ||
    o.value.toLowerCase().includes(search.toLowerCase())
  );

  // Reset highlight when filtered list changes
  useEffect(() => {
    setHighlightedIndex(-1);
  }, [search]);

  // Scroll highlighted item into view
  useEffect(() => {
    if (highlightedIndex >= 0) {
      itemRefs.current[highlightedIndex]?.scrollIntoView({ block: "nearest" });
    }
  }, [highlightedIndex]);

  // Close on click outside
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
        setSearch("");
        setHighlightedIndex(-1);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);


  function handleKeyDown(e: React.KeyboardEvent) {
    if (!open) {
      if (e.key === "ArrowDown" || e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        setOpen(true);
        setHighlightedIndex(0);
      }
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlightedIndex(i => Math.min(i + 1, filtered.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlightedIndex(i => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (highlightedIndex >= 0 && filtered[highlightedIndex]) {
        onChange(filtered[highlightedIndex].value);
        setOpen(false);
        setSearch("");
        setHighlightedIndex(-1);
      }
    } else if (e.key === "Escape") {
      setOpen(false);
      setSearch("");
      setHighlightedIndex(-1);
    }
  }

  const selected = options.find(o => o.value === value);

  return (
    <div ref={ref} style={{ position: "relative" }} onKeyDown={handleKeyDown}>
      <button
        type="button"
        onClick={() => {
          setOpen(o => !o);
          setSearch("");
          setHighlightedIndex(-1);
        }}
        style={{
          width: "100%",
          textAlign: "left",
          padding: "8px 12px",
          background: "rgba(255,255,255,0.6)",
          border: "1px solid rgba(132,177,121,0.2)",
          borderRadius: 8,
          fontSize: 12,
          color: selected ? "var(--text)" : "var(--text-tertiary)",
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 8,
          transition: "border-color 0.15s",
          fontFamily: "inherit",
        }}
      >
        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {selected ? selected.label : placeholder}
        </span>
        <svg
          width="10" height="10" viewBox="0 0 12 12" fill="none"
          style={{ flexShrink: 0, transform: open ? "rotate(180deg)" : "none", transition: "transform 0.15s" }}
        >
          <path d="M2 4l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      </button>

      {open && (
        <>
        <div style={{
          position: "absolute",
          top: "calc(100% + 4px)",
          left: 0, right: 0,
          background: "#F4F2EE",
          border: "1px solid rgba(132,177,121,0.25)",
          borderRadius: 8,
          boxShadow: "0 4px 20px rgba(44,58,40,0.12)",
          zIndex: 200,
          overflow: "hidden",
        }}>
          {options.length > 2 && (
            <div style={{ padding: "6px 8px", borderBottom: "1px solid rgba(132,177,121,0.15)" }}>
              <input
                autoFocus
                type="text"
                placeholder="Search..."
                value={search}
                onChange={e => setSearch(e.target.value)}
                style={{
                  width: "100%",
                  padding: "5px 8px",
                  border: "1px solid rgba(132,177,121,0.2)",
                  borderRadius: 6,
                  fontSize: 11.5,
                  background: "rgba(255,255,255,0.8)",
                  outline: "none",
                  boxSizing: "border-box",
                  fontFamily: "inherit",
                }}
              />
            </div>
          )}
          <div ref={listRef} style={{ maxHeight: 180, overflowY: "auto" }}>
            {filtered.length === 0 ? (
              <div style={{ padding: "8px 12px", fontSize: 11.5, color: "var(--text-tertiary)" }}>No results</div>
            ) : filtered.map((opt, i) => {
              const isSelected = opt.value === value;
              const isHighlighted = i === highlightedIndex;
              return (
                <button
                  key={opt.value}
                  ref={el => { itemRefs.current[i] = el; }}
                  type="button"
                  onClick={() => { onChange(opt.value); setOpen(false); setSearch(""); setHighlightedIndex(-1); }}
                  onMouseEnter={() => setHighlightedIndex(i)}
                  onMouseLeave={() => setHighlightedIndex(-1)}
                  style={{
                    display: "block",
                    width: "100%",
                    textAlign: "left",
                    padding: "8px 12px",
                    background: isHighlighted
                      ? "rgba(132,177,121,0.2)"
                      : isSelected
                      ? "rgba(132,177,121,0.12)"
                      : "transparent",
                    border: "none",
                    cursor: "pointer",
                    fontFamily: "inherit",
                    transition: "background 0.1s",
                  }}
                >
                  <div style={{ fontSize: 12, fontWeight: isSelected ? 600 : 400, color: "var(--text)" }}>
                    {opt.label}
                  </div>
                  <div style={{ fontSize: 10, color: "var(--text-tertiary)", marginTop: 1 }}>
                    {opt.value}
                  </div>
                </button>
              );
            })}
          </div>
        </div>
        </>
      )}
    </div>
  );
}
