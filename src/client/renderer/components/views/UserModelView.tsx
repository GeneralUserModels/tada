import { useEffect } from "react";
import { useAppContext } from "../../context/AppContext";
import { useTraining } from "../../hooks/useTraining";
import { requestPrediction } from "../../api/client";
import { TrainingTile, InferenceTile } from "../dashboard/PipelineTile";
import { PredictionCard } from "../dashboard/PredictionCard";
import { RewardsChart } from "../dashboard/RewardsChart";

export function UserModelView() {
  const { state, dispatch } = useAppContext();
  const training = useTraining();

  useEffect(() => {
    training.syncFromServer(state.trainingActive);
  }, [state.trainingActive]);

  const isTinker = (state.settings["model_type"] ?? "prompted") === "powernap";

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
    await requestPrediction();
  };

  return (
    <div id="usermodel-view" className="view active">
      <section className="glass-card">
        <div className="card-header">
          <h2>User Model</h2>
        </div>
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
      </section>
    </div>
  );
}
