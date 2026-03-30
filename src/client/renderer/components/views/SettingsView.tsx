import { useState, useEffect } from "react";
import { useAppContext } from "../../context/AppContext";
import { useTraining } from "../../hooks/useTraining";
import { updateSettings, startInference, requestPrediction } from "../../api/client";
import { TrainingTile, InferenceTile } from "../dashboard/PipelineTile";
import { PredictionCard } from "../dashboard/PredictionCard";
import { RewardsChart } from "../dashboard/RewardsChart";
import { AdvancedLLMSection, ADVANCED_ROWS } from "../shared/AdvancedLLMSection";
import { ModelDropdown, LLM_MODELS, TINKER_MODELS } from "../shared/ModelDropdown";
import { CollapsibleSection } from "../shared/CollapsibleSection";

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
  keys.add("tabracadabra_hold_threshold");
  keys.add("tabracadabra_model");
  keys.add("tabracadabra_api_key");
  return Array.from(keys);
}


export function SettingsView() {
  const { state, dispatch } = useAppContext();
  const [values, setValues] = useState<Record<string, string>>({});
  const training = useTraining();

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

  useEffect(() => {
    training.syncFromServer(state.trainingActive);
  }, [state.trainingActive]);

  const handleSave = async () => {
    const data: Record<string, unknown> = {};
    for (const key of allKeys()) {
      const val = (values[key] ?? "").trim();
      if (val) {
        data[key] = val;
      }
    }
    if ("tabracadabra_hold_threshold" in data) {
      data["tabracadabra_hold_threshold"] = parseFloat(data["tabracadabra_hold_threshold"] as string) || 1.0;
    }
    if (Object.keys(data).length > 0) {
      await updateSettings(data);
    }
  };

  const handleLLMModelChange = (val: string) => {
    setValues(v => ({ ...v, reward_llm: val, label_model: val, filter_model: val, tabracadabra_model: val }));
  };

  const handleStartTraining = async () => {
    dispatch({ type: "SET_TRAINING_ACTIVE", active: true });
    await training.startTraining();
  };

  const handleStopTraining = async () => {
    await training.stopTraining();
    dispatch({ type: "SET_TRAINING_ACTIVE", active: false });
  };

  const handleGenerate = async () => {
    dispatch({ type: "PREDICTION_REQUESTED" });
    await startInference();
    await requestPrediction();
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

          <AdvancedLLMSection values={values} setValues={setValues}>
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

      <CollapsibleSection title="User Model">
        <div className="training-section">
          <div className="status-bar" style={{ marginBottom: "16px" }}>
            <div className="stat-pill">
              <span className="stat-label">Labels</span>
              <span className="stat-value">{state.labels}</span>
            </div>
            {isTinker && (
              <div className="stat-pill">
                <span className="stat-label">Step</span>
                <span className="stat-value">{state.step}</span>
              </div>
            )}
          </div>
          <div className="controls-grid" style={{ marginBottom: "16px" }}>
            {isTinker && (
              <TrainingTile
                state={training.state}
                onStart={handleStartTraining}
                onStop={handleStopTraining}
              />
            )}
            <InferenceTile generating={state.generating} onGenerate={handleGenerate} />
            <PredictionCard prediction={state.prediction} />
            {isTinker && <RewardsChart data={state.rewardHistory} elboScore={state.elboScore} />}
          </div>
        </div>
      </CollapsibleSection>

      <CollapsibleSection title="Tabracadabra">
        <div className="settings-group">
          <div className="model-row">
            <span className="model-row-label">Hold Threshold (s)</span>
            <div className="model-row-fields">
              <label className="field">
                <input
                  type="number"
                  step="0.1"
                  min="0.1"
                  placeholder="1.0"
                  value={values["tabracadabra_hold_threshold"] ?? ""}
                  onChange={(e) => setValues(v => ({ ...v, tabracadabra_hold_threshold: e.target.value }))}
                />
              </label>
            </div>
          </div>
        </div>
      </CollapsibleSection>
    </div>
  );
}

