import React, { useState, useEffect } from "react";
import { useAppContext } from "../../context/AppContext";
import { useFeatureFlag } from "../../featureFlags";
import { getSettings, updateSettings } from "../../api/client";
import { AdvancedLLMSection, ADVANCED_ROWS } from "../shared/AdvancedLLMSection";
import { ModelDropdown, LLM_MODELS, AGENT_MODELS, TINKER_MODELS } from "../shared/ModelDropdown";


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
  keys.add("moments_agent_api_key");
  keys.add("memory_agent_model");
  keys.add("memory_agent_api_key");
  keys.add("seeker_model");
  keys.add("seeker_api_key");
  keys.add("agent_model");
  keys.add("agent_api_key");
  keys.add("tabracadabra_enabled");
  keys.add("moments_enabled");
  keys.add("memory_enabled");
  keys.add("seeker_enabled");
  return Array.from(keys);
}


export function SettingsView() {
  const { state, dispatch } = useAppContext();
  const momentsEnabled = useFeatureFlag("moments");
  const memoryEnabled = useFeatureFlag("memory");
  const seekerFlagEnabled = useFeatureFlag("seeker");
  const tabracadabraEnabled = useFeatureFlag("tabracadabra");
  const tinkerEnabled = useFeatureFlag("tinker");
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
      data[key] = val;
    }
    // boolean fields
    data["tabracadabra_enabled"] = (values["tabracadabra_enabled"] ?? "true") === "true";
    data["moments_enabled"] = (values["moments_enabled"] ?? "true") === "true";
    data["memory_enabled"] = (values["memory_enabled"] ?? "true") === "true";
    data["seeker_enabled"] = (values["seeker_enabled"] ?? "true") === "true";
    if (Object.keys(data).length > 0) {
      await updateSettings(data);
      const fresh = await getSettings();
      dispatch({ type: "LOAD_SETTINGS", settings: fresh as Record<string, unknown> });
    }
  };

  const handleLLMModelChange = (val: string) => {
    setValues(v => ({ ...v, reward_llm: val, label_model: val, filter_model: val, tabracadabra_model: val }));
  };

  const handleAgentModelChange = (val: string) => {
    setValues(v => ({ ...v, agent_model: val, moments_agent_model: val, memory_agent_model: val, seeker_model: val }));
  };

  const handleAgentApiKeyChange = (val: string) => {
    setValues(v => ({ ...v, agent_api_key: val, moments_agent_api_key: val, memory_agent_api_key: val, seeker_api_key: val }));
  };

  const hasUnsavedChanges = allKeys().some((key) => {
    const saved = state.settings[key];
    const current = values[key];
    return String(saved ?? "") !== String(current ?? "");
  });

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
            <span className="model-row-label">Labeling LM <span className="required-tag">Required</span></span>
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
            <span className="model-row-label">Agent LM <span className="required-tag">Required</span></span>
            <div className="model-row-fields">
              <label className="field">
                <span>Model</span>
                <ModelDropdown
                  value={values["agent_model"] ?? ""}
                  onChange={handleAgentModelChange}
                  options={AGENT_MODELS}
                  placeholder="Select a model"
                />
              </label>
              <label className="field">
                <span>API Key</span>
                <input
                  type="text"
                  placeholder="sk-ant-..."
                  value={values["agent_api_key"] ?? ""}
                  onChange={(e) => handleAgentApiKeyChange(e.target.value)}
                />
              </label>
            </div>
          </div>

          {momentsEnabled && (
          <div className="model-row">
            <span className="model-row-label">Tada</span>
            <label style={{ position: "relative", display: "inline-block", width: 36, height: 20, cursor: "pointer" }}>
              <input
                type="checkbox"
                checked={(values["moments_enabled"] ?? "true") === "true"}
                style={{ opacity: 0, width: 0, height: 0, position: "absolute" }}
                onChange={(e) => setValues(v => ({ ...v, moments_enabled: e.target.checked ? "true" : "false" }))}
              />
              <span style={{
                position: "absolute", inset: 0,
                background: (values["moments_enabled"] ?? "true") === "true" ? "#84B179" : "rgba(132,177,121,0.15)",
                borderRadius: 20, transition: "background 0.2s",
              }} />
              <span style={{
                position: "absolute", height: 14, width: 14, left: 3, bottom: 3,
                background: "#fff", borderRadius: "50%", transition: "transform 0.2s",
                boxShadow: "0 1px 3px rgba(0,0,0,0.15)",
                transform: (values["moments_enabled"] ?? "true") === "true" ? "translateX(16px)" : "translateX(0)",
              }} />
            </label>
          </div>
          )}
          {memoryEnabled && (
          <div className="model-row" style={{ marginTop: 10 }}>
            <span className="model-row-label">Pensieve</span>
            <label style={{ position: "relative", display: "inline-block", width: 36, height: 20, cursor: "pointer" }}>
              <input
                type="checkbox"
                checked={(values["memory_enabled"] ?? "true") === "true"}
                style={{ opacity: 0, width: 0, height: 0, position: "absolute" }}
                onChange={(e) => setValues(v => ({ ...v, memory_enabled: e.target.checked ? "true" : "false" }))}
              />
              <span style={{
                position: "absolute", inset: 0,
                background: (values["memory_enabled"] ?? "true") === "true" ? "#84B179" : "rgba(132,177,121,0.15)",
                borderRadius: 20, transition: "background 0.2s",
              }} />
              <span style={{
                position: "absolute", height: 14, width: 14, left: 3, bottom: 3,
                background: "#fff", borderRadius: "50%", transition: "transform 0.2s",
                boxShadow: "0 1px 3px rgba(0,0,0,0.15)",
                transform: (values["memory_enabled"] ?? "true") === "true" ? "translateX(16px)" : "translateX(0)",
              }} />
            </label>
          </div>
          )}
          {seekerFlagEnabled && (
          <div className="model-row" style={{ marginTop: 10 }}>
            <span className="model-row-label">Seeker</span>
            <label style={{ position: "relative", display: "inline-block", width: 36, height: 20, cursor: "pointer" }}>
              <input
                type="checkbox"
                checked={(values["seeker_enabled"] ?? "true") === "true"}
                style={{ opacity: 0, width: 0, height: 0, position: "absolute" }}
                onChange={(e) => setValues(v => ({ ...v, seeker_enabled: e.target.checked ? "true" : "false" }))}
              />
              <span style={{
                position: "absolute", inset: 0,
                background: (values["seeker_enabled"] ?? "true") === "true" ? "#84B179" : "rgba(132,177,121,0.15)",
                borderRadius: 20, transition: "background 0.2s",
              }} />
              <span style={{
                position: "absolute", height: 14, width: 14, left: 3, bottom: 3,
                background: "#fff", borderRadius: "50%", transition: "transform 0.2s",
                boxShadow: "0 1px 3px rgba(0,0,0,0.15)",
                transform: (values["seeker_enabled"] ?? "true") === "true" ? "translateX(16px)" : "translateX(0)",
              }} />
            </label>
          </div>
          )}
          {tabracadabraEnabled && (
          <div className="model-row" style={{ marginTop: 10 }}>
            <span className="model-row-label">Tabracadabra</span>
            <label style={{ position: "relative", display: "inline-block", width: 36, height: 20, cursor: "pointer" }}>
              <input
                type="checkbox"
                checked={(values["tabracadabra_enabled"] ?? "true") === "true"}
                style={{ opacity: 0, width: 0, height: 0, position: "absolute" }}
                onChange={(e) => setValues(v => ({ ...v, tabracadabra_enabled: e.target.checked ? "true" : "false" }))}
              />
              <span style={{
                position: "absolute", inset: 0,
                background: (values["tabracadabra_enabled"] ?? "true") === "true" ? "#84B179" : "rgba(132,177,121,0.15)",
                borderRadius: 20, transition: "background 0.2s",
              }} />
              <span style={{
                position: "absolute", height: 14, width: 14, left: 3, bottom: 3,
                background: "#fff", borderRadius: "50%", transition: "transform 0.2s",
                boxShadow: "0 1px 3px rgba(0,0,0,0.15)",
                transform: (values["tabracadabra_enabled"] ?? "true") === "true" ? "translateX(16px)" : "translateX(0)",
              }} />
            </label>
          </div>
          )}

          <AdvancedLLMSection values={values} setValues={setValues}>
            {tinkerEnabled && (
              <>
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

      {hasUnsavedChanges && (
        <div style={{
          position: "fixed", bottom: 16, left: 216, right: 16,
          background: "#fff", border: "1px solid rgba(132,177,121,0.25)",
          borderRadius: 12,
          boxShadow: "0 4px 24px rgba(44,58,40,0.12), 0 1px 4px rgba(0,0,0,0.06)",
          padding: "12px 20px", display: "flex", alignItems: "center",
          justifyContent: "space-between", zIndex: 100,
        }}>
          <span style={{ fontSize: 13, fontWeight: 500, color: "var(--text, #2C3A28)" }}>
            Careful, you have unsaved changes!
          </span>
          <button className="pill-btn pill-start" onClick={handleSave}>
            Save Changes
          </button>
        </div>
      )}
    </div>
  );
}

