import React, { useState } from "react";
import { ModelDropdown, LLM_MODELS, ModelOption } from "./ModelDropdown";

export const ADVANCED_ROWS: { label: string; modelKey: string; apiKeyKey: string }[] = [
  { label: "Reward LM",        modelKey: "reward_llm",            apiKeyKey: "reward_llm_api_key" },
  { label: "Labeling LM",      modelKey: "label_model",           apiKeyKey: "label_model_api_key" },
  { label: "Filter LM",        modelKey: "filter_model",          apiKeyKey: "filter_model_api_key" },
  { label: "Ta-Da LM",         modelKey: "moments_agent_model",   apiKeyKey: "moments_agent_api_key" },
  { label: "Tabracadabra LM",  modelKey: "tabracadabra_model",    apiKeyKey: "tabracadabra_api_key" },
];

interface ModelApiKeyRowProps {
  label: string;
  modelKey: string;
  apiKeyKey: string;
  values: Record<string, string>;
  setValues: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  options?: ModelOption[];
  modelPlaceholder?: string;
  apiKeyPlaceholder?: string;
}

export function ModelApiKeyRow({
  label, modelKey, apiKeyKey, values, setValues,
  options = LLM_MODELS,
  modelPlaceholder = "Select a model",
  apiKeyPlaceholder = "Leave blank to use shared key",
}: ModelApiKeyRowProps) {
  return (
    <div className="model-row">
      <span className="model-row-label">{label}</span>
      <div className="model-row-fields">
        <label className="field">
          <span>Model</span>
          <ModelDropdown
            value={values[modelKey] ?? ""}
            onChange={(val) => setValues(v => ({ ...v, [modelKey]: val }))}
            options={options}
            placeholder={modelPlaceholder}
          />
        </label>
        <label className="field">
          <span>API Key</span>
          <input
            type="text"
            placeholder={apiKeyPlaceholder}
            value={values[apiKeyKey] ?? ""}
            onChange={(e) => setValues(v => ({ ...v, [apiKeyKey]: e.target.value }))}
          />
        </label>
      </div>
    </div>
  );
}

interface Props {
  values: Record<string, string>;
  setValues: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  children?: React.ReactNode;
}

export function AdvancedLLMSection({ values, setValues, children }: Props) {
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
            <ModelApiKeyRow key={row.modelKey} {...row} values={values} setValues={setValues} modelPlaceholder="Use shared model" />
          ))}
          {children}
        </div>
      )}
    </div>
  );
}
