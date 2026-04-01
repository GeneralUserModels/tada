import { useState } from "react";
import React from "react";

interface Props {
  title: string;
  children: React.ReactNode;
}

export function CollapsibleSection({ title, children }: Props) {
  const [open, setOpen] = useState(false);

  return (
    <section className="glass-card">
      <button
        className="collapsible-header"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        <h2>{title}</h2>
        <svg
          width="16"
          height="16"
          viewBox="0 0 16 16"
          fill="none"
          style={{ transform: open ? "rotate(180deg)" : "rotate(0deg)", transition: "transform 0.2s" }}
        >
          <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      </button>
      {open && children}
    </section>
  );
}
