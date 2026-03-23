import { useState, useEffect } from "react";
import { useAppContext } from "../../context/AppContext";
import { useTraining } from "../../hooks/useTraining";
import { TrainingTile, InferenceTile } from "../dashboard/PipelineTile";
import { PredictionCard } from "../dashboard/PredictionCard";
import { RewardsChart } from "../dashboard/RewardsChart";
import { AdvancedLLMSection, ADVANCED_ROWS } from "../shared/AdvancedLLMSection";
import { ModelDropdown, LLM_MODELS, TINKER_MODELS } from "../shared/ModelDropdown";

const MODEL_ROWS: { label: string; modelKey: string; modelPlaceholder: string; apiKeyKey: string; apiKeyPlaceholder: string; required?: boolean }[] = [
  { label: "LLM",    modelKey: "reward_llm",  modelPlaceholder: "gemini/gemini-3-flash-preview",   apiKeyKey: "default_llm_api_key",  apiKeyPlaceholder: "AIza...", required: true },
  { label: "Tinker", modelKey: "model",       modelPlaceholder: "Qwen/Qwen3-VL-30B-A3B-Instruct", apiKeyKey: "tinker_api_key",  apiKeyPlaceholder: "tk-..." },
];

// All keys used across all sections
function allKeys(): string[] {
  const keys = new Set<string>();
  for (const row of MODEL_ROWS) { keys.add(row.modelKey); keys.add(row.apiKeyKey); }
  for (const row of ADVANCED_ROWS) { keys.add(row.modelKey); keys.add(row.apiKeyKey); }
  keys.add("hf_token"); keys.add("wandb_api_key");
  // Also sync LLM model to label_model and filter_model
  keys.add("label_model");
  keys.add("filter_model");
  return Array.from(keys);
}


export function SettingsView() {
  const { state, dispatch } = useAppContext();
  const [values, setValues] = useState<Record<string, string>>({});
  const [trainingOpen, setTrainingOpen] = useState(false);
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
        data[key] = key === "fps" ? parseInt(val, 10) : val;
      }
    }
    if (Object.keys(data).length > 0) {
      await window.powernap.updateSettings(data);
    }
  };

  // When the shared LLM model changes, sync it to label_model and filter_model too
  const handleLLMModelChange = (val: string) => {
    setValues(v => ({ ...v, reward_llm: val, label_model: val, filter_model: val }));
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
    await window.powernap.startInference();
    await window.powernap.requestPrediction();
  };

  return (
    <div id="settings-view" className="view active">
      <section className="glass-card">
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

          <AdvancedLLMSection values={values} setValues={setValues} />

          <div className="model-row">
            <span className="model-row-label">Tinker <span className="optional-tag">optional</span></span>
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
        </div>

        <div className="settings-footer">
          <button className="pill-btn pill-start" onClick={handleSave}>
            Save Changes
          </button>
        </div>
      </section>

      <section className="glass-card">
        <button
          className="collapsible-header"
          onClick={() => setTrainingOpen((o) => !o)}
          aria-expanded={trainingOpen}
        >
          <h2>Online Training</h2>
          <svg
            width="16"
            height="16"
            viewBox="0 0 16 16"
            fill="none"
            style={{ transform: trainingOpen ? "rotate(180deg)" : "rotate(0deg)", transition: "transform 0.2s" }}
          >
            <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </button>

        {trainingOpen && (
          <div className="training-section">
            <div className="status-bar" style={{ marginBottom: "16px" }}>
              <div className="stat-pill">
                <span className="stat-label">Labels</span>
                <span className="stat-value">{state.labels}</span>
              </div>
              <div className="stat-pill">
                <span className="stat-label">Queue</span>
                <span className="stat-value">{state.queue}</span>
              </div>
              <div className="stat-pill">
                <span className="stat-label">Step</span>
                <span className="stat-value">{state.step}</span>
              </div>
              <div className="stat-pill">
                <span className="stat-label">Buffer</span>
                <span className="stat-value">{state.buffer}</span>
              </div>
            </div>

            <div className="controls-grid" style={{ marginBottom: "16px" }}>
              <TrainingTile
                state={training.state}
                onStart={handleStartTraining}
                onStop={handleStopTraining}
              />
              <InferenceTile
                generating={state.generating}
                onGenerate={handleGenerate}
              />
            </div>

            <div className="split-row" style={{ marginBottom: "16px" }}>
              <PredictionCard prediction={state.prediction} />
              <RewardsChart data={state.rewardHistory} elboScore={state.elboScore} />
            </div>

          </div>
        )}
      </section>
    </div>
  );
}
