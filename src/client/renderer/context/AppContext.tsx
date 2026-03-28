import { createContext, useContext, useReducer, useRef, useEffect, ReactNode } from "react";

// ── Types ─────────────────────────────────────────────────────

export type ActiveView = "connectors" | "tada" | "settings";

export interface HistoryItem {
  id: number;
  type: "prediction" | "label" | "training";
  text: string;
  timestamp: string;
}

export interface RewardPoint {
  step: number;
  accuracy: number;
  formatting: number;
  combined: number;
}

export interface AppState {
  connected: boolean;
  trainingActive: boolean;
  labels: number;
  queue: number;
  step: number;
  buffer: number;
  activeView: ActiveView;
  prediction: { actions?: string; error?: string; timestamp?: string } | null;
  generating: boolean;
  rewardHistory: RewardPoint[];
  elboScore: string | null;
  historyItems: HistoryItem[];
  momentResults: MomentResult[];
  settings: Record<string, unknown>;
  updateVersion: string | null;
  permModal: { connectorName: string } | null;
}

type AppAction =
  | { type: "NAVIGATE"; view: ActiveView }
  | { type: "SERVER_READY"; status: StatusData }
  | { type: "STATUS_UPDATE"; data: StatusData }
  | { type: "SET_TRAINING_ACTIVE"; active: boolean }
  | { type: "PREDICTION"; data: PredictionData }
  | { type: "PREDICTION_REQUESTED" }
  | { type: "SCORE"; data: ScoreData }
  | { type: "ELBO_SCORE"; data: ElboScoreData }
  | { type: "TRAINING_STEP"; data: TrainingStepData }
  | { type: "LABEL"; data: LabelData }
  | { type: "SEED_HISTORY"; history: TrainingStepData[] }
  | { type: "SEED_LABEL_HISTORY"; history: { text: string; timestamp: number }[] }
  | { type: "LOAD_SETTINGS"; settings: Record<string, unknown> }
  | { type: "UPDATE_DOWNLOADED"; version: string }
  | { type: "UPDATE_DISMISSED" }
  | { type: "LOAD_MOMENTS"; results: MomentResult[] }
  | { type: "MOMENT_COMPLETED"; result: MomentResult }
  | { type: "OPEN_PERM_MODAL"; connectorName: string }
  | { type: "CLOSE_PERM_MODAL" };

let historyCounter = 0;

function addHistoryItem(
  items: HistoryItem[],
  type: HistoryItem["type"],
  text: string,
  timestamp: string
): HistoryItem[] {
  const next = [{ id: historyCounter++, type, text, timestamp }, ...items];
  return next.length > 100 ? next.slice(0, 100) : next;
}

const initialState: AppState = {
  connected: false,
  trainingActive: false,
  labels: 0,
  queue: 0,
  step: 0,
  buffer: 0,
  activeView: "connectors",
  prediction: null,
  generating: false,
  rewardHistory: [],
  elboScore: null,
  historyItems: [],
  momentResults: [],
  settings: {},
  updateVersion: null,
  permModal: null,
};

function reducer(state: AppState, action: AppAction): AppState {
  switch (action.type) {
    case "NAVIGATE":
      return { ...state, activeView: action.view };

    case "SERVER_READY":
      return {
        ...state,
        connected: true,
        trainingActive: action.status.training_active ?? false,
        labels: action.status.labels_processed ?? 0,
        queue: action.status.untrained_batches ?? 0,
        step: action.status.step_count ?? 0,
        buffer: action.status.context_buffer_size ?? 0,
      };

    case "STATUS_UPDATE":
      return {
        ...state,
        trainingActive: action.data.training_active ?? state.trainingActive,
        labels: action.data.labels_processed ?? state.labels,
        queue: action.data.untrained_batches ?? state.queue,
        buffer: action.data.context_buffer_size ?? state.buffer,
      };

    case "SET_TRAINING_ACTIVE":
      return { ...state, trainingActive: action.active };

    case "PREDICTION":
      return {
        ...state,
        generating: false,
        prediction: action.data,
        historyItems: action.data.error
          ? state.historyItems
          : addHistoryItem(state.historyItems, "prediction", action.data.actions ?? "", action.data.timestamp ?? ""),
      };

    case "PREDICTION_REQUESTED":
      return { ...state, generating: true };

    case "SCORE": {
      const pt: RewardPoint = {
        step: state.rewardHistory.length,
        accuracy: action.data.accuracy ?? 0,
        formatting: action.data.formatting ?? 0,
        combined: action.data.reward ?? 0,
      };
      return { ...state, rewardHistory: [...state.rewardHistory, pt] };
    }

    case "ELBO_SCORE": {
      const mean = (action.data.logprob_reward_mean ?? 0).toFixed(4);
      const std = (action.data.logprob_reward_std ?? 0).toFixed(4);
      return { ...state, elboScore: `ELBO ${mean} ± ${std}` };
    }

    case "TRAINING_STEP": {
      const d = action.data;
      const pt: RewardPoint = {
        step: d.step ?? 0,
        accuracy: d.accuracy_mean ?? 0,
        formatting: d.formatting_mean ?? 0,
        combined: d.reward_mean ?? 0,
      };
      const text = `Step ${d.step}: loss=${(d.loss ?? 0).toFixed(4)}, reward=${(d.reward_mean ?? 0).toFixed(4)}`;
      return {
        ...state,
        step: d.step ?? state.step,
        rewardHistory: [...state.rewardHistory, pt],
        historyItems: addHistoryItem(state.historyItems, "training", text, ""),
      };
    }

    case "LABEL":
      return {
        ...state,
        labels: action.data.count ?? state.labels,
        historyItems: addHistoryItem(state.historyItems, "label", action.data.text ?? "", ""),
      };

    case "SEED_LABEL_HISTORY": {
      let items = state.historyItems;
      for (const entry of action.history) {
        items = addHistoryItem(items, "label", entry.text, "");
      }
      // addHistoryItem prepends; reverse the seeded items so oldest appears last
      return { ...state, historyItems: items };
    }

    case "SEED_HISTORY": {
      const pts = action.history.map((h) => ({
        step: h.step ?? 0,
        accuracy: h.accuracy_mean ?? 0,
        formatting: h.formatting_mean ?? 0,
        combined: h.reward_mean ?? 0,
      }));
      const lastStep = pts.length > 0 ? pts[pts.length - 1].step : state.step;
      return { ...state, rewardHistory: pts, step: lastStep };
    }

    case "LOAD_SETTINGS":
      return { ...state, settings: action.settings };

    case "UPDATE_DOWNLOADED":
      return { ...state, updateVersion: action.version };

    case "UPDATE_DISMISSED":
      return { ...state, updateVersion: null };

    case "LOAD_MOMENTS":
      return { ...state, momentResults: action.results };

    case "MOMENT_COMPLETED":
      return { ...state, momentResults: [action.result, ...state.momentResults] };

    case "OPEN_PERM_MODAL":
      return { ...state, permModal: { connectorName: action.connectorName } };

    case "CLOSE_PERM_MODAL":
      return { ...state, permModal: null };

    default:
      return state;
  }
}

// ── Context ───────────────────────────────────────────────────

interface AppContextValue {
  state: AppState;
  dispatch: React.Dispatch<AppAction>;
}

const AppContext = createContext<AppContextValue | null>(null);

export function useAppContext() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useAppContext must be used within AppProvider");
  return ctx;
}

// ── Provider ──────────────────────────────────────────────────

export function AppProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const registered = useRef(false);

  useEffect(() => {
    if (registered.current) return;
    registered.current = true;

    window.powernap.onServerReady(async () => {
      try {
        const status = await window.powernap.getStatus();
        dispatch({ type: "SERVER_READY", status });

        try {
          const history = await window.powernap.getTrainingHistory();
          if (Array.isArray(history)) {
            dispatch({ type: "SEED_HISTORY", history });
          }
        } catch { /* metrics may not exist yet */ }

        try {
          const labelHistory = await window.powernap.getLabelHistory();
          if (Array.isArray(labelHistory) && labelHistory.length > 0) {
            dispatch({ type: "SEED_LABEL_HISTORY", history: labelHistory });
          }
        } catch { /* label history may not exist yet */ }

        try {
          const settings = await window.powernap.getSettings();
          dispatch({ type: "LOAD_SETTINGS", settings });
        } catch { /* settings fetch failed */ }
      } catch { /* server not running yet */ }
    });

    window.powernap.onStatusUpdate((data) => {
      dispatch({ type: "STATUS_UPDATE", data });
    });

    window.powernap.onPrediction((data) => {
      dispatch({ type: "PREDICTION", data });
    });

    window.powernap.onPredictionRequested(() => {
      dispatch({ type: "PREDICTION_REQUESTED" });
    });

    window.powernap.onScore((data) => {
      dispatch({ type: "SCORE", data });
    });

    window.powernap.onElboScore((data) => {
      dispatch({ type: "ELBO_SCORE", data });
    });

    window.powernap.onTrainingStep((data) => {
      dispatch({ type: "TRAINING_STEP", data });
    });

    window.powernap.onLabel((data) => {
      dispatch({ type: "LABEL", data });
    });

    window.powernap.onMomentCompleted((data) => {
      dispatch({ type: "MOMENT_COMPLETED", result: data as MomentResult });
    });

    window.powernap.onUpdateDownloaded((data) => {
      dispatch({ type: "UPDATE_DOWNLOADED", version: data.version });
    });
  }, []);

  return (
    <AppContext.Provider value={{ state, dispatch }}>
      {children}
    </AppContext.Provider>
  );
}
