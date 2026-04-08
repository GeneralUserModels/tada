import { useEffect } from "react";
import { useAppContext } from "../../context/AppContext";
import { useTraining } from "../../hooks/useTraining";
import { TrainingTile, InferenceTile } from "../dashboard/PipelineTile";
import { PredictionCard } from "../dashboard/PredictionCard";
import { RewardsChart } from "../dashboard/RewardsChart";

export function DashboardView() {
  const { state, dispatch } = useAppContext();
  const training = useTraining();

  // Sync training tile state from server status
  useEffect(() => {
    training.syncFromServer(state.trainingActive);
  }, [state.trainingActive]);

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
    await window.tada.startInference();
    await window.tada.requestPrediction();
  };

  return (
    <div id="dashboard-view" className="view active">
      <section className="glass-card">
        <div className="card-header">
          <h2>Pipeline</h2>
        </div>
        <div className="controls-grid">
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
      </section>

      <div className="split-row">
        <PredictionCard prediction={state.prediction} />
        <RewardsChart data={state.rewardHistory} elboScore={state.elboScore} />
      </div>
    </div>
  );
}
