import { useState } from "react";

export const ADVANCED_ROWS: { label: string; modelKey: string; apiKeyKey: string }[] = [
  { label: "Reward LM",   modelKey: "reward_llm",   apiKeyKey: "reward_llm_api_key" },
  { label: "Labeling LM", modelKey: "label_model",  apiKeyKey: "label_model_api_key" },
  { label: "Filter LM",   modelKey: "filter_model", apiKeyKey: "filter_model_api_key" },
];

interface Props {
  values: Record<string, string>;
  setValues: (updater: (prev: Record<string, string>) => Record<string, string>) => void;
}

export function AdvancedLLMSection({ values, setValues }: Props) {
  const [open, setOpen] = useState(false);

  return (
    <div style={{ marginBottom: 14 }}>
      <button
        className="advanced-toggle"
        onClick={() => setOpen(o => !o)}
        aria-expanded={open}
      >
        <svg
          width="12" height="12" viewBox="0 0 12 12" fill="none"
          style={{ transform: open ? "rotate(90deg)" : "rotate(0deg)", transition: "transform 0.15s" }}
        >
          <path d="M4 2l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
        Advanced
      </button>

      {open && (
        <div className="advanced-section">
          <p className="advanced-hint">Override model and/or API key per LLM. Leave blank to use the shared values above.</p>
          {ADVANCED_ROWS.map((row) => (
            <div key={row.modelKey} className="model-row">
              <span className="model-row-label">{row.label}</span>
              <div className="model-row-fields">
                <label className="field">
                  <span>Model</span>
                  <input
                    type="text"
                    placeholder="Leave blank to use shared model"
                    value={values[row.modelKey] ?? ""}
                    onChange={(e) => setValues(v => ({ ...v, [row.modelKey]: e.target.value }))}
                  />
                </label>
                <label className="field">
                  <span>API Key</span>
                  <input
                    type="text"
                    placeholder="Leave blank to use shared key"
                    value={values[row.apiKeyKey] ?? ""}
                    onChange={(e) => setValues(v => ({ ...v, [row.apiKeyKey]: e.target.value }))}
                  />
                </label>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
