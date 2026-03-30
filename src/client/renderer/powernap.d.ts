/** Global type for the powernap context bridge exposed by preload.ts */

declare global {

interface StatusData {
  training_active: boolean;
  labels_processed: number;
  step_count: number;
}

interface PredictionData {
  actions?: string;
  error?: string;
  timestamp?: string;
}

interface ScoreData {
  accuracy: number;
  formatting: number;
  reward: number;
}

interface ElboScoreData {
  logprob_reward_mean: number;
  logprob_reward_std: number;
}

interface TrainingStepData {
  step: number;
  loss: number;
  accuracy_mean: number;
  formatting_mean: number;
  reward_mean: number;
}

interface LabelData {
  count: number;
  text: string;
}

interface UpdateData {
  version: string;
}

interface ConnectorInfo {
  enabled: boolean;
  available: boolean;
  error?: string | null;
  requires_auth?: "google" | "outlook" | null;
}

interface ConnectorPermissionInfo {
  title: string;
  body: string;
  steps: string[];
  fixUrl: string;
  hasRequest: boolean;
}

interface PowerNapAPI {
  // App lifecycle
  onServerReady: (cb: (data: { url: string }) => void) => void;
  onPredictionRequested: (cb: () => void) => void;

  // Overlay
  onOverlayPrediction: (cb: (data: PredictionData) => void) => void;
  onOverlayWaiting: (cb: () => void) => void;
  onOverlayFlushing: (cb: () => void) => void;
  resizeOverlay: (height: number) => void;

  // Onboarding — screen permission (Electron-only) + completion signal
  checkScreenPermission: () => Promise<string>;
  openScreenSettings: () => Promise<unknown>;
  requestScreenPermission: () => Promise<string>;
  openNotifSettings: () => Promise<unknown>;
  onboardingComplete: () => void;

  // Connectors (OS-level permission checks only)
  openFdaSettings: (name?: string) => Promise<unknown>;
  getConnectorPermissionInfo: (name: string) => Promise<ConnectorPermissionInfo | null>;
  requestConnectorPermission: (name: string) => Promise<boolean>;
  checkConnectorPermission: (name: string) => Promise<boolean>;

  // Auto-update
  onUpdateDownloaded: (cb: (data: UpdateData) => void) => void;
  onUpdateError: (cb: (msg: string) => void) => void;
  installNow: () => Promise<unknown>;
  installOnNextLaunch: () => Promise<unknown>;
  dismissUpdate: () => Promise<unknown>;
  checkForUpdates: () => Promise<unknown>;

  // Bootstrap (setup window)
  onBootstrapProgress: (cb: (msg: string, pct: number) => void) => void;
  onBootstrapLog: (cb: (line: string) => void) => void;
  onBootstrapError: (cb: (errMsg: string) => void) => void;
  onBootstrapComplete: (cb: () => void) => void;
  retryBootstrap: () => void;
}

  interface Window {
    powernap: PowerNapAPI;
  }

} // end declare global

declare module "react" {
  interface CSSProperties {
    WebkitAppRegion?: "drag" | "no-drag";
  }
}

export {};
