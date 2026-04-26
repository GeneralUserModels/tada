import React, { createContext, useContext, useReducer, useRef, useEffect, ReactNode } from "react";
import * as api from "../api/client";
import * as sse from "../api/sse";

// ── Types ─────────────────────────────────────────────────────

export type ActiveView = "activity" | "tada" | "memex" | "seeker" | "chat" | "usermodel" | "settings";

export interface HistoryItem {
  id: number;
  type: "prediction" | "label" | "training";
  text: string;
  timestamp: string;
  denseCaption?: string;
}

export interface RewardPoint {
  step: number;
  accuracy: number;
  formatting: number;
  combined: number;
}

export interface AgentActivityInfo {
  agent: string;
  message: string;
  slug?: string;
  frequency?: string;
  numTurns: number | null;
  maxTurns: number | null;
}

export interface AppState {
  connected: boolean;
  servicesReady: boolean;
  trainingActive: boolean;
  labels: number;
  step: number;
  activeView: ActiveView;
  prediction: { actions?: string; error?: string; timestamp?: string } | null;
  generating: boolean;
  rewardHistory: RewardPoint[];
  elboScore: string | null;
  historyItems: HistoryItem[];
  settings: Record<string, unknown>;
  updateVersion: string | null;
  seekerHasQuestions: boolean;
  tadaHasNew: boolean;
  memexHasNew: boolean;
  updateProgress: number | null;
  updateReady: boolean;
  updateInstalling: boolean;
  updateError: string | null;
  agentActivities: Record<string, AgentActivityInfo>;
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
  | { type: "SEED_LABEL_HISTORY"; history: { text: string; timestamp: number; dense_caption?: string }[] }
  | { type: "LOAD_SETTINGS"; settings: Record<string, unknown> }
  | { type: "UPDATE_AVAILABLE"; version: string }
  | { type: "SEEKER_QUESTIONS_READY" }
  | { type: "SEEKER_QUESTIONS_CLEARED" }
  | { type: "TADA_NEW_MOMENT" }
  | { type: "MEMEX_UPDATED" }
  | { type: "UPDATE_PROGRESS"; percent: number }
  | { type: "UPDATE_DOWNLOADED" }
  | { type: "UPDATE_INSTALLING" }
  | { type: "UPDATE_ERROR"; message: string }
  | { type: "UPDATE_DISMISSED" }
  | { type: "AGENT_ACTIVITY"; data: { agent: string; message: string | null; slug?: string | null; frequency?: string | null; num_turns?: number | null; max_turns?: number | null } }
  | { type: "SET_AGENT_ACTIVITIES"; activities: Record<string, AgentActivity> };

let historyCounter = 0;

function addHistoryItem(
  items: HistoryItem[],
  type: HistoryItem["type"],
  text: string,
  timestamp: string,
  denseCaption?: string
): HistoryItem[] {
  const next = [{ id: historyCounter++, type, text, timestamp, denseCaption }, ...items];
  return next.length > 100 ? next.slice(0, 100) : next;
}

const initialState: AppState = {
  connected: false,
  servicesReady: false,
  trainingActive: false,
  labels: 0,
  step: 0,
  activeView: "chat",
  prediction: null,
  generating: false,
  rewardHistory: [],
  elboScore: null,
  historyItems: [],
  settings: {},
  updateVersion: null,
  seekerHasQuestions: false,
  tadaHasNew: false,
  memexHasNew: false,
  updateProgress: null,
  updateReady: false,
  updateInstalling: false,
  updateError: null,
  agentActivities: {},
};

function reducer(state: AppState, action: AppAction): AppState {
  switch (action.type) {
    case "NAVIGATE":
      return {
        ...state,
        activeView: action.view,
        tadaHasNew: action.view === "tada" ? false : state.tadaHasNew,
        memexHasNew: action.view === "memex" ? false : state.memexHasNew,
      };

    case "SERVER_READY":
      return {
        ...state,
        connected: true,
        servicesReady: action.status.services_started ?? false,
        trainingActive: action.status.training_active ?? false,
        labels: action.status.labels_processed ?? 0,
        step: action.status.step_count ?? 0,
      };

    case "STATUS_UPDATE":
      return {
        ...state,
        servicesReady: action.data.services_started ?? state.servicesReady,
        trainingActive: action.data.training_active ?? state.trainingActive,
        labels: action.data.labels_processed ?? state.labels,
      };

    case "SET_TRAINING_ACTIVE":
      return { ...state, trainingActive: action.active };

    case "PREDICTION":
      if ((action.data as Record<string, unknown>).source === "auto") return state;
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
        historyItems: addHistoryItem(state.historyItems, "label", action.data.text ?? "", "", action.data.dense_caption),
      };

    case "SEED_LABEL_HISTORY": {
      let items = state.historyItems;
      for (const entry of action.history) {
        items = addHistoryItem(items, "label", entry.text, "", entry.dense_caption);
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

    case "UPDATE_AVAILABLE":
      return { ...state, updateVersion: action.version, updateError: null };

    case "UPDATE_PROGRESS":
      return { ...state, updateProgress: action.percent };

    case "UPDATE_DOWNLOADED":
      return { ...state, updateReady: true, updateProgress: 100 };

    case "UPDATE_INSTALLING":
      return { ...state, updateInstalling: true };

    case "UPDATE_ERROR":
      return { ...state, updateError: action.message, updateInstalling: false };

    case "UPDATE_DISMISSED":
      return { ...state, updateVersion: null, updateReady: false, updateProgress: null, updateInstalling: false, updateError: null };

    case "SEEKER_QUESTIONS_READY":
      return { ...state, seekerHasQuestions: true };

    case "SEEKER_QUESTIONS_CLEARED":
      return { ...state, seekerHasQuestions: false };

    case "TADA_NEW_MOMENT":
      return { ...state, tadaHasNew: true };

    case "MEMEX_UPDATED":
      return { ...state, memexHasNew: true };

    case "AGENT_ACTIVITY": {
      const { agent, message, slug, frequency, num_turns, max_turns } = action.data;
      if (!message) {
        const { [agent]: _, ...rest } = state.agentActivities;
        return { ...state, agentActivities: rest };
      }
      return {
        ...state,
        agentActivities: {
          ...state.agentActivities,
          [agent]: {
            agent,
            message,
            slug: slug ?? undefined,
            frequency: frequency ?? undefined,
            numTurns: num_turns ?? null,
            maxTurns: max_turns ?? null,
          },
        },
      };
    }

    case "SET_AGENT_ACTIVITIES": {
      const next: Record<string, AgentActivityInfo> = {};
      for (const [agent, info] of Object.entries(action.activities)) {
        if (!info.message) continue;
        next[agent] = {
          agent,
          message: info.message,
          slug: info.slug ?? undefined,
          frequency: info.frequency ?? undefined,
          numTurns: info.num_turns ?? null,
          maxTurns: info.max_turns ?? null,
        };
      }
      return { ...state, agentActivities: next };
    }

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

    // SSE events — direct from Python, no IPC hop
    sse.on<StatusData>("status",            (data) => dispatch({ type: "STATUS_UPDATE", data }));
    sse.on<PredictionData>("prediction",    (data) => dispatch({ type: "PREDICTION", data }));
    sse.on<ScoreData>("score",              (data) => dispatch({ type: "SCORE", data }));
    sse.on<ElboScoreData>("elbo_score",     (data) => dispatch({ type: "ELBO_SCORE", data }));
    sse.on<TrainingStepData>("training_step", (data) => dispatch({ type: "TRAINING_STEP", data }));
    sse.on<LabelData>("label",              (data) => dispatch({ type: "LABEL", data }));
    sse.on("seeker_questions_ready", () => dispatch({ type: "SEEKER_QUESTIONS_READY" }));
    sse.on("moment_completed", () => dispatch({ type: "TADA_NEW_MOMENT" }));
    sse.on("memory_updated", () => dispatch({ type: "MEMEX_UPDATED" }));
    sse.on<{ agent: string; message: string | null; slug?: string | null; frequency?: string | null; num_turns?: number | null; max_turns?: number | null }>(
      "agent_activity",
      (data) => {
        console.log("[sse] agent_activity", data);
        dispatch({ type: "AGENT_ACTIVITY", data });
      },
    );

    // server:ready — main sends URL once server is up; we initialize api + sse then seed state
    window.tada.onServerReady(async ({ url }: { url: string }) => {
      api.setServerUrl(url);
      sse.connect();

      try {
        const status = await api.getStatus();
        dispatch({ type: "SERVER_READY", status });
        dispatch({ type: "SET_AGENT_ACTIVITIES", activities: status.active_agents ?? {} });
        console.log("[app] server ready, url:", url);

        try {
          const history = await api.getTrainingHistory();
          if (Array.isArray(history)) {
            dispatch({ type: "SEED_HISTORY", history });
          }
        } catch { /* metrics may not exist yet */ }

        try {
          const labelHistory = await api.getLabelHistory();
          if (Array.isArray(labelHistory) && labelHistory.length > 0) {
            dispatch({ type: "SEED_LABEL_HISTORY", history: labelHistory });
          }
        } catch { /* label history may not exist yet */ }

        try {
          const settings = await api.getSettings();
          dispatch({ type: "LOAD_SETTINGS", settings: settings as Record<string, unknown> });
        } catch { /* settings fetch failed */ }

        try {
          const seekerStatus = await api.getSeekerStatus();
          if (seekerStatus.has_questions && !seekerStatus.questions_answered) {
            dispatch({ type: "SEEKER_QUESTIONS_READY" });
          }
        } catch { /* seeker may not be enabled */ }

        try {
          const moments = await api.getMomentsResults();
          const hasUnread = moments.some(
            (r) => !r.dismissed && (!r.last_viewed || new Date(r.completed_at) > new Date(r.last_viewed))
          );
          if (hasUnread) dispatch({ type: "TADA_NEW_MOMENT" });
        } catch { /* moments may not be enabled */ }
      } catch (e) { console.error("[app] getStatus failed:", e); }
    });

    window.tada.onUpdateAvailable((data) => {
      dispatch({ type: "UPDATE_AVAILABLE", version: data.version });
    });
    window.tada.onUpdateProgress((data) => {
      dispatch({ type: "UPDATE_PROGRESS", percent: data.percent });
    });
    window.tada.onUpdateDownloaded(() => {
      dispatch({ type: "UPDATE_DOWNLOADED" });
    });
    window.tada.onUpdateError((data) => {
      dispatch({ type: "UPDATE_ERROR", message: data.message });
    });
  }, []);

  return (
    <AppContext.Provider value={{ state, dispatch }}>
      {children}
    </AppContext.Provider>
  );
}
