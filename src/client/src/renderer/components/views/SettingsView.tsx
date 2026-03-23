import { useState, useEffect } from "react";
import { useAppContext } from "../../context/AppContext";
import { useTraining } from "../../hooks/useTraining";
import { TrainingTile, InferenceTile } from "../dashboard/PipelineTile";
import { PredictionCard } from "../dashboard/PredictionCard";
import { RewardsChart } from "../dashboard/RewardsChart";

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
  const { state, dispatch } = useAppContext();
  const [values, setValues] = useState<Record<string, string>>({});
  const [trainingOpen, setTrainingOpen] = useState(false);
  const training = useTraining();

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

  useEffect(() => {
    training.syncFromServer(state.trainingActive);
  }, [state.trainingActive]);

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
