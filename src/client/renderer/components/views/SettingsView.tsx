import { useState, useEffect } from "react";
import { useAppContext } from "../../context/AppContext";
import { updateSettings } from "../../api/client";
import { AdvancedLLMSection, ADVANCED_ROWS } from "../shared/AdvancedLLMSection";
import { ModelDropdown, LLM_MODELS, TINKER_MODELS, TADA_MODELS } from "../shared/ModelDropdown";


// All keys used across all sections
function allKeys(): string[] {
  const keys = new Set<string>();
  for (const row of ADVANCED_ROWS) { keys.add(row.modelKey); keys.add(row.apiKeyKey); }
  keys.add("default_llm_api_key");
  keys.add("reward_llm");
  keys.add("label_model");
  keys.add("filter_model");
  keys.add("model_type");
  keys.add("model");
  keys.add("tinker_api_key");
  keys.add("hf_token");
  keys.add("wandb_api_key");
  keys.add("moments_agent_model");
  keys.add("moments_agent_model_api_key");
  keys.add("tabracadabra_enabled");
  return Array.from(keys);
}


export function SettingsView() {
  const { state } = useAppContext();
  const [values, setValues] = useState<Record<string, string>>({});

  useEffect(() => {
    const populated: Record<string, string> = {};
    for (const key of allKeys()) {
      const val = state.settings[key];
      if (val !== undefined && val !== null && val !== "") {
        populated[key] = String(val);
      }
    }
    setValues(populated);
  }, [state.settings]);

  const handleSave = async () => {
    const data: Record<string, unknown> = {};
    for (const key of allKeys()) {
      const val = (values[key] ?? "").trim();
      if (val) {
        data[key] = val;
      }
    }
    // tabracadabra_enabled is a boolean
    data["tabracadabra_enabled"] = values["tabracadabra_enabled"] === "true";
    if (Object.keys(data).length > 0) {
      await updateSettings(data);
    }
  };

  const handleLLMModelChange = (val: string) => {
    setValues(v => ({ ...v, reward_llm: val, label_model: val, filter_model: val, tabracadabra_model: val }));
  };

  const modelType = values["model_type"] ?? "prompted";
  const isTinker = modelType === "powernap";

  return (
    <div id="settings-view" className="view active">
      <section className="glass-card" style={{ position: "relative", zIndex: 1 }}>
        <div className="card-header">
          <h2>Configuration</h2>
        </div>

        <div className="settings-group">
          <div className="model-row">
            <span className="model-row-label">LLM <span className="required-tag">Required</span></span>
            <div className="model-row-fields">
              <label className="field">
                <span>Model</span>
                <ModelDropdown
                  value={values["reward_llm"] ?? ""}
                  onChange={handleLLMModelChange}
                  options={LLM_MODELS}
                  placeholder="Select a model"
                />
              </label>
              <label className="field">
                <span>API Key</span>
                <input
                  type="text"
                  placeholder="AIza..."
                  value={values["default_llm_api_key"] ?? ""}
                  onChange={(e) => setValues(v => ({ ...v, default_llm_api_key: e.target.value }))}
                />
              </label>
            </div>
          </div>

          <div className="model-row">
            <span className="model-row-label">Ta-Da</span>
            <label style={{ position: "relative", display: "inline-block", width: 36, height: 20, cursor: "pointer" }}>
              <input
                type="checkbox"
                checked={state.settings.moments_enabled !== false}
                style={{ opacity: 0, width: 0, height: 0, position: "absolute" }}
                onChange={async () => {
                  const enabled = state.settings.moments_enabled === false;
                  await updateSettings({ moments_enabled: enabled } as Record<string, unknown>);
                  dispatch({ type: "LOAD_SETTINGS", settings: { ...state.settings, moments_enabled: enabled } });
                }}
              />
              <span style={{
                position: "absolute", inset: 0,
                background: state.settings.moments_enabled !== false ? "#84B179" : "rgba(132,177,121,0.15)",
                borderRadius: 20, transition: "background 0.2s",
              }} />
              <span style={{
                position: "absolute", height: 14, width: 14, left: 3, bottom: 3,
                background: "#fff", borderRadius: "50%", transition: "transform 0.2s",
                boxShadow: "0 1px 3px rgba(0,0,0,0.15)",
                transform: state.settings.moments_enabled !== false ? "translateX(16px)" : "translateX(0)",
              }} />
            </label>
          </div>
          <div className="model-row" style={{ marginTop: 10 }}>
            <span className="model-row-label">Tabracadabra</span>
            <div style={{ display: "flex", gap: 4, background: "rgba(0,0,0,0.05)", borderRadius: 8, padding: 3, width: "fit-content" }}>
              {(["true", "false"] as const).map((val) => {
                const active = (values["tabracadabra_enabled"] ?? "true") === val;
                return (
                  <button
                    key={val}
                    type="button"
                    onClick={() => setValues(v => ({ ...v, tabracadabra_enabled: val }))}
                    style={{
                      padding: "5px 14px",
                      borderRadius: 6,
                      border: "none",
                      fontSize: 12,
                      fontFamily: "inherit",
                      cursor: "pointer",
                      fontWeight: active ? 600 : 400,
                      background: active ? "white" : "transparent",
                      color: active ? "var(--text)" : "var(--text-tertiary)",
                      boxShadow: active ? "0 1px 4px rgba(0,0,0,0.1)" : "none",
                      transition: "all 0.15s",
                    }}
                  >
                    {val === "true" ? "Enabled" : "Disabled"}
                  </button>
                );
              })}
            </div>
          </div>

          <AdvancedLLMSection values={values} setValues={setValues}>
            {/* Ta-Da LM */}
            <div className="model-row">
              <span className="model-row-label">Ta-Da LM</span>
              <div className="model-row-fields">
                <label className="field">
                  <span>Model</span>
                  <ModelDropdown
                    value={values["moments_agent_model"] ?? ""}
                    onChange={(val) => setValues(v => ({ ...v, moments_agent_model: val }))}
                    options={TADA_MODELS}
                    placeholder="Select a model"
                  />
                </label>
                <label className="field">
                  <span>API Key</span>
                  <input
                    type="text"
                    placeholder="Leave blank to use shared key"
                    value={values["moments_agent_model_api_key"] ?? ""}
                    onChange={(e) => setValues(v => ({ ...v, moments_agent_model_api_key: e.target.value }))}
                  />
                </label>
              </div>
            </div>

            {/* User model type */}
            <div className="model-row" style={{ marginTop: 10 }}>
              <span className="model-row-label">User Model</span>
              <div style={{ display: "flex", gap: 4, background: "rgba(0,0,0,0.05)", borderRadius: 8, padding: 3, width: "fit-content" }}>
                {(["prompted", "powernap"] as const).map((type) => (
                  <button
                    key={type}
                    type="button"
                    onClick={() => setValues(v => ({ ...v, model_type: type }))}
                    style={{
                      padding: "5px 14px",
                      borderRadius: 6,
                      border: "none",
                      fontSize: 12,
                      fontFamily: "inherit",
                      cursor: "pointer",
                      fontWeight: modelType === type ? 600 : 400,
                      background: modelType === type ? "white" : "transparent",
                      color: modelType === type ? "var(--text)" : "var(--text-tertiary)",
                      boxShadow: modelType === type ? "0 1px 4px rgba(0,0,0,0.1)" : "none",
                      transition: "all 0.15s",
                    }}
                  >
                    {type === "prompted" ? "Prompted" : "Tinker"}
                  </button>
                ))}
              </div>
            </div>

            {isTinker && (
              <>
                <div className="model-row">
                  <span className="model-row-label">Tinker</span>
                  <div className="model-row-fields">
                    <label className="field">
                      <span>Model</span>
                      <ModelDropdown
                        value={values["model"] ?? ""}
                        onChange={(val) => setValues(v => ({ ...v, model: val }))}
                        options={TINKER_MODELS}
                        placeholder="Select a model"
                      />
                    </label>
                    <label className="field">
                      <span>API Key</span>
                      <input
                        type="text"
                        placeholder="tml-..."
                        value={values["tinker_api_key"] ?? ""}
                        onChange={(e) => setValues(v => ({ ...v, tinker_api_key: e.target.value }))}
                      />
                    </label>
                  </div>
                </div>
                <div className="model-row">
                  <span className="model-row-label">W&amp;B <span className="optional-tag">optional</span></span>
                  <div className="model-row-fields">
                    <label className="field">
                      <span>API Key</span>
                      <input type="text" placeholder="wandb-..." value={values["wandb_api_key"] ?? ""} onChange={(e) => setValues(v => ({ ...v, wandb_api_key: e.target.value }))} />
                    </label>
                    <label className="field">
                      <span>HuggingFace Token</span>
                      <input type="text" placeholder="hf_..." value={values["hf_token"] ?? ""} onChange={(e) => setValues(v => ({ ...v, hf_token: e.target.value }))} />
                    </label>
                  </div>
                </div>
              </>
            )}
          </AdvancedLLMSection>
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

