import { useState, useEffect } from "react";
import { useAppContext } from "../../context/AppContext";

const SETTINGS_FIELDS: { id: string; key: string; label: string; type: string; placeholder: string }[] = [
  { id: "set-gemini-key",   key: "gemini_api_key",  label: "Gemini",            type: "text",   placeholder: "sk-..." },
  { id: "set-tinker-key",   key: "tinker_api_key",  label: "Tinker",            type: "text",   placeholder: "tk-..." },
  { id: "set-hf-token",     key: "hf_token",        label: "HuggingFace",       type: "text",   placeholder: "hf_..." },
  { id: "set-wandb-key",    key: "wandb_api_key",   label: "Weights & Biases",  type: "text",   placeholder: "wandb-..." },
  { id: "set-model",        key: "model",           label: "Base Model",        type: "text",   placeholder: "Qwen/Qwen3-VL-30B-A3B-Instruct" },
  { id: "set-reward-llm",   key: "reward_llm",      label: "Reward LLM",        type: "text",   placeholder: "gemini/gemini-3-flash-preview" },
  { id: "set-fps",          key: "fps",             label: "Recording FPS",     type: "number", placeholder: "5" },
];

export function SettingsView() {
  const { state } = useAppContext();
  const [values, setValues] = useState<Record<string, string>>({});

  useEffect(() => {
    const populated: Record<string, string> = {};
    for (const f of SETTINGS_FIELDS) {
      const val = state.settings[f.key];
      if (val !== undefined && val !== null && val !== "") {
        populated[f.key] = String(val);
      }
    }
    setValues(populated);
  }, [state.settings]);

  const handleSave = async () => {
    const data: Record<string, unknown> = {};
    for (const f of SETTINGS_FIELDS) {
      const val = (values[f.key] ?? "").trim();
      if (val) {
        data[f.key] = f.key === "fps" ? parseInt(val, 10) : val;
      }
    }
    if (Object.keys(data).length > 0) {
      await window.powernap.updateSettings(data);
    }
  };

  const apiKeyFields = SETTINGS_FIELDS.slice(0, 4);
  const modelFields = SETTINGS_FIELDS.slice(4);

  return (
    <div id="settings-view" className="view active">
      <section className="glass-card">
        <div className="card-header">
          <h2>Configuration</h2>
        </div>
        <div className="settings-sections">
          <div className="settings-group">
            <h3>API Keys</h3>
            {apiKeyFields.map((f) => (
              <label key={f.id} className="field">
                <span>{f.label}</span>
                <input
                  type="text"
                  id={f.id}
                  placeholder={f.placeholder}
                  value={values[f.key] ?? ""}
                  onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))}
                />
              </label>
            ))}
          </div>
          <div className="settings-group">
            <h3>Model</h3>
            {modelFields.map((f) => (
              <label key={f.id} className="field">
                <span>{f.label}</span>
                <input
                  type={f.type}
                  id={f.id}
                  placeholder={f.placeholder}
                  min={f.key === "fps" ? 1 : undefined}
                  max={f.key === "fps" ? 60 : undefined}
                  value={values[f.key] ?? ""}
                  onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))}
                />
              </label>
            ))}
          </div>
        </div>
        <div className="settings-footer">
          <button className="pill-btn pill-start" onClick={handleSave}>
            Save Changes
          </button>
        </div>
      </section>
    </div>
  );
}
