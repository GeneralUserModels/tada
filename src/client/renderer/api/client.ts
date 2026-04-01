/** REST client — thin fetch wrapper for the PowerNap server. */

export { setServerUrl, getServerUrl } from "../../shared/api-core";
import { request } from "../../shared/api-core";

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
export const startGoogleAuth = () =>
  request("POST", "/api/auth/google/start") as Promise<{ ok: boolean }>;
export const disconnectGoogle = () => request("DELETE", "/api/auth/google");
export const startOutlookAuth = () => request("POST", "/api/auth/outlook/start");
export const disconnectOutlook = () => request("DELETE", "/api/auth/outlook");

// ── Onboarding ───────────────────────────────────────────────
export const getOnboardingStatus = () =>
  request("GET", "/api/onboarding/status") as Promise<{ complete: boolean }>;
export const completeOnboarding = () => request("POST", "/api/onboarding/complete");
export const checkNotificationsPermission = () =>
  request("GET", "/api/permissions/notifications") as Promise<{ granted: boolean }>;
export const checkFilesystemPermission = () =>
  request("GET", "/api/permissions/filesystem") as Promise<{ granted: boolean }>;
