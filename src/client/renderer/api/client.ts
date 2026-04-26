/** REST client — thin fetch wrapper for the Tada server. */

export { setServerUrl, getServerUrl } from "../../shared/api-core";
import { request, requestText } from "../../shared/api-core";

// ── User model control ────────────────────────────────────────
export const startTraining = () => request("POST", "/api/user_models/training/start");
export const stopTraining = () => request("POST", "/api/user_models/training/stop");

// ── Status / Settings ────────────────────────────────────────
export const getStatus = () => request("GET", "/api/status") as Promise<StatusData>;
export const getSettings = () => request("GET", "/api/settings");
export const updateSettings = (data: Record<string, unknown>) =>
  request("PUT", "/api/settings", data);

// ── Training ─────────────────────────────────────────────────
export const getTrainingHistory = () => request("GET", "/api/user_models/history");
export const getLabelHistory = () => request("GET", "/api/connectors/label-history");

// ── Connectors ───────────────────────────────────────────────
export const getConnectors = () =>
  request("GET", "/api/connectors") as Promise<Record<string, { enabled: boolean; error?: string | null; requires_auth?: string | null }>>;

export const updateConnector = (name: string, enabled: boolean) =>
  request("PUT", `/api/connectors/${name}`, { enabled });

// ── Prediction ───────────────────────────────────────────────
export const requestPrediction = () =>
  request("POST", "/api/user_models/prediction");

// ── Auth (Google + Outlook OAuth — runs in Python) ────────────
export const startGoogleSignIn = () =>
  request("POST", "/api/auth/google/signin") as Promise<{ name: string; email: string }>;
export const getGoogleUser = () =>
  request("GET", "/api/auth/google/user") as Promise<{ name: string; email: string } | null>;
export const startGoogleAuth = () =>
  request("POST", "/api/auth/google/start") as Promise<{ ok: boolean }>;
export const disconnectGoogle = () => request("DELETE", "/api/auth/google");
export const startOutlookAuth = () => request("POST", "/api/auth/outlook/start");
export const disconnectOutlook = () => request("DELETE", "/api/auth/outlook");

// ── Moments ─────────────────────────────────────────────
export const getMomentsTasks = () => request("GET", "/api/moments/tasks");
export const getMomentsResults = (includeDismissed = false) =>
  request("GET", `/api/moments/results${includeDismissed ? "?include_dismissed=true" : ""}`) as Promise<MomentResult[]>;

export const updateMomentState = (slug: string, data: { dismissed?: boolean; pinned?: boolean; thumbs?: "up" | "down" | null }) =>
  request("PUT", `/api/moments/${slug}/state`, data);

export const updateMomentSchedule = (slug: string, data: { frequency: string; schedule: string }) =>
  request("PUT", `/api/moments/${slug}/schedule`, data);

export const recordMomentView = (slug: string) =>
  request("POST", `/api/moments/${slug}/view`);

export const recordMomentViewEnd = (slug: string, data: { duration_ms: number }) =>
  request("POST", `/api/moments/${slug}/view-end`, data);

export const endMomentFeedback = (slug: string) =>
  request("POST", `/api/moments/${slug}/feedback/end`);

export const rerunMoment = (slug: string) =>
  request("POST", `/api/moments/${slug}/rerun`);

// ── Seeker ──────────────────────────────────────────────────
export const getSeekerStatus = () =>
  request("GET", "/api/seeker/status") as Promise<SeekerStatus>;
export const getSeekerConversation = () =>
  request("GET", "/api/seeker/conversation") as Promise<{ active: boolean; messages: SeekerMessage[] }>;
export const endSeekerConversation = () =>
  request("POST", "/api/seeker/end");
export const getSeekerHistory = () =>
  request("GET", "/api/seeker/history") as Promise<{ filename: string; date: string }[]>;
export const getSeekerPastConversation = (filename: string) =>
  request("GET", `/api/seeker/history/${filename}`) as Promise<{ filename: string; messages: SeekerMessage[] }>;

// ── Chat assistant ──────────────────────────────────────────
export const getChatOptions = () =>
  request("GET", "/api/chat/options") as Promise<ChatOptions>;
export const listChatSessions = () =>
  request("GET", "/api/chat/sessions") as Promise<ChatSessionMeta[]>;
export const createChatSession = (body: { model: string; effort: string; title?: string }) =>
  request("POST", "/api/chat/sessions", body) as Promise<ChatSessionMeta>;
export const getChatSession = (id: string) =>
  request("GET", `/api/chat/sessions/${id}`) as Promise<{ meta: ChatSessionMeta; messages: ChatItem[] }>;
export const updateChatSession = (id: string, body: { effort?: string; title?: string }) =>
  request("PUT", `/api/chat/sessions/${id}`, body) as Promise<ChatSessionMeta>;
export const deleteChatSession = (id: string) =>
  request("DELETE", `/api/chat/sessions/${id}`);

// ── Memory wiki ─────────────────────────────────────────────
export const getMemoryPages = (q?: string) =>
  request("GET", q ? `/api/memory/pages?q=${encodeURIComponent(q)}` : "/api/memory/pages") as Promise<{ path: string; title: string; confidence: number | null; last_updated: string | null; category: string | null }[]>;

export const getMemoryPage = (path: string) =>
  requestText("GET", `/api/memory/pages/${path}`);

export const updateMemoryPage = (path: string, content: string) =>
  request("PUT", `/api/memory/pages/${path}`, { content });

export const deleteMemoryPage = (path: string) =>
  request("DELETE", `/api/memory/pages/${path}`);

export const getMemoryStatus = () =>
  request("GET", "/api/memory/status") as Promise<{ exists: boolean; last_ingest: string | null; last_lint: string | null; page_count: number }>;

export const getMemoryLog = () =>
  requestText("GET", "/api/memory/log");

// ── Onboarding ───────────────────────────────────────────────
export const getGoogleConnectorStatus = () =>
  request("GET", "/api/auth/google/status") as Promise<{ connected: boolean }>;
export const getOutlookConnectorStatus = () =>
  request("GET", "/api/auth/outlook/status") as Promise<{ connected: boolean }>;
export const getOnboardingStatus = () =>
  request("GET", "/api/onboarding/status") as Promise<{
    complete: boolean;
    seen_steps: string[];
    enabled_connectors: string[];
  }>;
export const finalizeOnboarding = () =>
  request("POST", "/api/onboarding/finalize");
export const completeOnboarding = (seenSteps: string[]) =>
  request("POST", "/api/onboarding/complete", { seen_steps: seenSteps });
export const getServicesStatus = () =>
  request("GET", "/api/services/status") as Promise<{
    services_started: boolean;
    tabracadabra_ready: boolean;
    screen_frame_fresh: boolean;
  }>;
export const checkNotificationsPermission = () =>
  request("GET", "/api/permissions/notifications") as Promise<{ granted: boolean }>;
export const checkFilesystemPermission = () =>
  request("GET", "/api/permissions/filesystem") as Promise<{ granted: boolean }>;
export const checkBrowserCookiesPermission = () =>
  request("GET", "/api/permissions/browser_cookies") as Promise<{ granted: boolean }>;
