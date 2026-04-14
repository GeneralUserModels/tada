/** REST client — thin fetch wrapper for the Tada server. */

export { setServerUrl, getServerUrl } from "../../shared/api-core";
import { request, requestText } from "../../shared/api-core";

// ── User model control ────────────────────────────────────────
export const startTraining = () => request("POST", "/api/user_models/training/start");
export const stopTraining = () => request("POST", "/api/user_models/training/stop");

// ── Status / Settings ────────────────────────────────────────
export const getStatus = () => request("GET", "/api/status");
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

export const updateMomentState = (slug: string, data: { dismissed?: boolean; pinned?: boolean }) =>
  request("PUT", `/api/moments/${slug}/state`, data);

export const updateMomentSchedule = (slug: string, data: { frequency: string; schedule: string }) =>
  request("PUT", `/api/moments/${slug}/schedule`, data);

export const recordMomentView = (slug: string) =>
  request("POST", `/api/moments/${slug}/view`);

export const recordMomentViewEnd = (slug: string, data: { duration_ms: number }) =>
  request("POST", `/api/moments/${slug}/view-end`, data);

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

// ── Memory wiki ─────────────────────────────────────────────
export const getMemoryPages = () =>
  request("GET", "/api/memory/pages") as Promise<{ path: string; title: string; confidence: number | null; last_updated: string | null; category: string | null }[]>;

export const getMemoryPage = (path: string) =>
  requestText("GET", `/api/memory/pages/${path}`);

export const updateMemoryPage = (path: string, content: string) =>
  request("PUT", `/api/memory/pages/${path}`, { content });

export const getMemoryStatus = () =>
  request("GET", "/api/memory/status") as Promise<{ exists: boolean; last_ingest: string | null; last_lint: string | null; page_count: number }>;

export const getMemoryLog = () =>
  requestText("GET", "/api/memory/log");

// ── Onboarding ───────────────────────────────────────────────
export const getOnboardingStatus = () =>
  request("GET", "/api/onboarding/status") as Promise<{ complete: boolean }>;
export const completeOnboarding = () => request("POST", "/api/onboarding/complete");
export const checkNotificationsPermission = () =>
  request("GET", "/api/permissions/notifications") as Promise<{ granted: boolean }>;
export const checkFilesystemPermission = () =>
  request("GET", "/api/permissions/filesystem") as Promise<{ granted: boolean }>;
export const checkBrowserCookiesPermission = () =>
  request("GET", "/api/permissions/browser_cookies") as Promise<{ granted: boolean }>;
