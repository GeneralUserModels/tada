import React from "react";

export function StepIndicator({ current, total }: { current: number; total: number }) {
  const items: JSX.Element[] = [];
  for (let i = 0; i < total; i++) {
    if (i > 0) items.push(<div key={`line-${i}`} className="step-line"></div>);
    items.push(
      <div
        key={`dot-${i}`}
        className={`step-dot${i === current ? " active" : i < current ? " done" : ""}`}
      ></div>
    );
  }
  return <div className="steps">{items}</div>;
}
