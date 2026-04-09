import React, { useState, useEffect, useRef } from "react";

export interface ModelOption {
  value: string;
  label: string;
}

export const LLM_MODELS: ModelOption[] = [
  { value: "gemini/gemini-3.1-flash-lite-preview",  label: "Gemini 3.1 Flash-Lite Preview" },
  { value: "openai/gpt-5.4-nano",                   label: "OpenAI GPT-5.4 Nano" },
  { value: "openai/gpt-4.1-nano",                   label: "OpenAI GPT-4.1 Nano" },
];

export const TADA_MODELS: ModelOption[] = [
  { value: "gemini/gemini-3.1-flash-lite-preview",  label: "Gemini 3.1 Flash-Lite Preview" },
  { value: "openai/gpt-5.4-nano",                   label: "OpenAI GPT-5.4 Nano" },
  { value: "openai/gpt-4.1-nano",                   label: "OpenAI GPT-4.1 Nano" },
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
  const listRef = useRef<HTMLDivElement>(null);
  const itemRefs = useRef<(HTMLButtonElement | null)[]>([]);

  const filtered = options.filter(o =>
    o.label.toLowerCase().includes(search.toLowerCase()) ||
    o.value.toLowerCase().includes(search.toLowerCase())
  );

  useEffect(() => { setHighlightedIndex(-1); }, [search]);

  useEffect(() => {
    if (highlightedIndex >= 0) {
      itemRefs.current[highlightedIndex]?.scrollIntoView({ block: "nearest" });
    }
  }, [highlightedIndex]);

  function close() {
    setOpen(false);
    setSearch("");
    setHighlightedIndex(-1);
  }

  function select(val: string) {
    onChange(val);
    close();
  }

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
        select(filtered[highlightedIndex].value);
      }
    } else if (e.key === "Escape") {
      close();
    }
  }

  const selected = options.find(o => o.value === value);

  return (
    <div style={{ position: "relative" }} onKeyDown={handleKeyDown}>
      {/* Backdrop — captures clicks outside the list, sits behind the list */}
      {open && (
        <div
          style={{ position: "fixed", inset: 0, zIndex: 199 }}
          onMouseDown={(e) => { e.preventDefault(); close(); }}
        />
      )}

      <button
        type="button"
        onMouseDown={(e) => {
          e.preventDefault(); // keep focus, prevent label forwarding
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
          {selected ? selected.label : value ? value : placeholder}
        </span>
        <svg
          width="10" height="10" viewBox="0 0 12 12" fill="none"
          style={{ flexShrink: 0, transform: open ? "rotate(180deg)" : "none", transition: "transform 0.15s" }}
        >
          <path d="M2 4l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      </button>

      {open && (
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
                onMouseDown={e => e.stopPropagation()} // don't let search input close via backdrop
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
                  onMouseDown={(e) => {
                    e.preventDefault(); // prevent label forwarding + focus shift
                    select(opt.value);
                  }}
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
      )}
    </div>
  );
}
