/**
 * SimpleDropdown — small custom-styled dropdown for {value, label} options.
 *
 * Reuses the .tada-dropdown* CSS so it visually matches the rest of the app.
 * Use this instead of native <select> in views that need a styled picker
 * without the Mac default chrome.
 */

import React, { useCallback, useEffect, useRef, useState } from "react";

export interface DropdownOption<V extends string = string> {
  value: V;
  label: string;
}

interface Props<V extends string> {
  value: V;
  options: readonly DropdownOption<V>[];
  onChange: (value: V) => void;
  className?: string;
  title?: string;
  disabled?: boolean;
}

export function SimpleDropdown<V extends string>({
  value,
  options,
  onChange,
  className,
  title,
  disabled,
}: Props<V>) {
  const [open, setOpen] = useState(false);
  const [highlighted, setHighlighted] = useState(-1);
  const ref = useRef<HTMLDivElement>(null);

  const select = useCallback(
    (v: V) => {
      onChange(v);
      setOpen(false);
    },
    [onChange],
  );

  useEffect(() => {
    if (!open) return;
    const idx = options.findIndex((o) => o.value === value);
    if (idx >= 0) setHighlighted(idx);
  }, [open, options, value]);

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        return;
      }
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setHighlighted((h) => Math.min(h + 1, options.length - 1));
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setHighlighted((h) => Math.max(h - 1, 0));
      }
      if (e.key === "Enter" && highlighted >= 0) {
        e.preventDefault();
        select(options[highlighted].value);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, highlighted, options, select]);

  const current = options.find((o) => o.value === value);

  return (
    <div className={`tada-dropdown${className ? " " + className : ""}`} ref={ref}>
      <button
        className="tada-dropdown-trigger"
        onClick={() => !disabled && setOpen((o) => !o)}
        type="button"
        title={title}
        disabled={disabled}
      >
        <span>{current?.label ?? value}</span>
        <svg
          width="10"
          height="10"
          viewBox="0 0 10 10"
          fill="none"
          style={{ transform: open ? "rotate(180deg)" : "none", transition: "transform 0.15s" }}
        >
          <path
            d="M2 3.5L5 6.5L8 3.5"
            stroke="currentColor"
            strokeWidth="1.2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>
      {open && (
        <>
          <div className="tada-dropdown-backdrop" onClick={() => setOpen(false)} />
          <div className="tada-dropdown-menu">
            {options.map((opt, i) => (
              <div
                key={opt.value}
                data-value={opt.value}
                className={`tada-dropdown-item${opt.value === value ? " selected" : ""}${
                  i === highlighted ? " highlighted" : ""
                }`}
                onMouseEnter={() => setHighlighted(i)}
                onClick={(e) => {
                  e.stopPropagation();
                  select(opt.value);
                }}
              >
                {opt.label}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
