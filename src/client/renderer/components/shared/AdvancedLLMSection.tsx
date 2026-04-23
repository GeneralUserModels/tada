import React, { useState } from "react";
import { ModelDropdown, LLM_MODELS, AGENT_MODELS, ModelOption } from "./ModelDropdown";

export const ADVANCED_ROWS: { label: string; modelKey: string; apiKeyKey: string; group: "llm" | "agent"; options?: ModelOption[] }[] = [
  { label: "Reward LM",        modelKey: "reward_llm",            apiKeyKey: "reward_llm_api_key",    group: "llm" },
  { label: "Labeling LM",      modelKey: "label_model",           apiKeyKey: "label_model_api_key",   group: "llm" },
  { label: "Filter LM",        modelKey: "filter_model",          apiKeyKey: "filter_model_api_key",  group: "llm" },
  { label: "Tada LM",          modelKey: "moments_agent_model",   apiKeyKey: "moments_agent_api_key", group: "agent", options: AGENT_MODELS },
  { label: "Memex LM",      modelKey: "memory_agent_model",    apiKeyKey: "memory_agent_api_key",  group: "agent", options: AGENT_MODELS },
  { label: "Seeker LM",        modelKey: "seeker_model",          apiKeyKey: "seeker_api_key",        group: "agent", options: AGENT_MODELS },
  { label: "Tabracadabra LM",  modelKey: "tabracadabra_model",    apiKeyKey: "tabracadabra_api_key",  group: "llm" },
];

export const LLM_ROWS = ADVANCED_ROWS.filter(r => r.group === "llm");
export const AGENT_ROWS = ADVANCED_ROWS.filter(r => r.group === "agent");

export function fanOut(rows: typeof ADVANCED_ROWS, field: "modelKey" | "apiKeyKey", value: string): Record<string, string> {
  return Object.fromEntries(rows.map(r => [r[field], value]));
}

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
  apiKeyPlaceholder = "Override shared key",
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
          <p className="advanced-hint">Override model and/or API key per LLM.</p>
          {ADVANCED_ROWS.map(({ options: rowOptions, ...row }) => (
            <ModelApiKeyRow key={row.modelKey} {...row} options={rowOptions} values={values} setValues={setValues} modelPlaceholder="Use shared model" />
          ))}
          {children}
        </div>
      )}
    </div>
  );
}
