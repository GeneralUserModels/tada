import { TrainingState } from "../../hooks/useTraining";

const stateLabels: Record<TrainingState, string> = {
  idle: "Idle",
  starting: "Starting\u2026",
  running: "Running",
  stopping: "Stopping\u2026",
};

interface TrainingTileProps {
  state: TrainingState;
  onStart: () => void;
  onStop: () => void;
}

export function TrainingTile({ state, onStart, onStop }: TrainingTileProps) {
  return (
    <div className={`control-tile${state === "running" ? " running" : ""}`}>
      <div className="tile-top">
        <div className="tile-icon training-icon">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path d="M2 11l3-4 3 2.5 4-6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </div>
        <span className="tile-label">Training</span>
      </div>
      <div className={`tile-status${state === "running" ? " active" : ""}${state === "starting" || state === "stopping" ? " transitioning" : ""}`}>
        {stateLabels[state]}
      </div>
      <div className="tile-actions">
        <button
          className="pill-btn pill-start"
          disabled={state !== "idle"}
          onClick={onStart}
        >
          Start
        </button>
        <button
          className="pill-btn pill-stop"
          disabled={state !== "running"}
          onClick={onStop}
        >
          Stop
        </button>
      </div>
    </div>
  );
}

interface InferenceTileProps {
  generating: boolean;
  onGenerate: () => void;
}

export function InferenceTile({ generating, onGenerate }: InferenceTileProps) {
  return (
    <div className={`control-tile${generating ? " running" : ""}`}>
      <div className="tile-top">
        <div className="tile-icon inference-icon">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path d="M7 2v4l3 2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
            <path d="M2.5 8.5A5 5 0 1012 7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
          </svg>
        </div>
        <span className="tile-label">Inference</span>
      </div>
      <div className={`tile-status${generating ? " transitioning" : ""}`}>
        {generating ? "Generating\u2026" : "Idle"}
      </div>
      <div className="tile-actions">
        <button
          className="pill-btn pill-start"
          disabled={generating}
          onClick={onGenerate}
        >
          {generating ? "Generating Predictions\u2026" : "Generate Predictions"}
        </button>
      </div>
    </div>
  );
}
