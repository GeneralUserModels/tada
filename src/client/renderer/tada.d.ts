/** Global type for the tada context bridge exposed by preload.ts */

declare global {

interface StatusData {
  services_started?: boolean;
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

interface MomentTask {
  slug: string;
  title: string;
  description: string;
  frequency: string;
  schedule: string;
  confidence: number;
  usefulness: number;
}

interface MomentResult {
  slug: string;
  title: string;
  description: string;
  completed_at: string;
  frequency: string;
  schedule: string;
  dismissed: boolean;
  pinned: boolean;
  view_count: number;
  time_spent_ms: number;
  last_viewed: string | null;
  schedule_override: string | null;
  frequency_override: string | null;
}

interface TadaAPI {
  // App lifecycle
  onServerReady: (cb: (data: { url: string }) => void) => void;

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

  // Moments (Ta-Da)
  getMomentsTasks: () => Promise<MomentTask[]>;
  getMomentsResults: () => Promise<MomentResult[]>;
  getServerUrl: () => Promise<string>;
  onMomentCompleted: (cb: (data: MomentResult) => void) => void;

  // Update check
  onUpdateAvailable: (cb: (data: UpdateData) => void) => void;
  dismissUpdate: () => void;
  checkForUpdates: () => Promise<unknown>;

  // External links
  openExternalUrl: (url: string) => Promise<boolean>;

  // Bootstrap (setup window)
  onBootstrapProgress: (cb: (msg: string, pct: number) => void) => void;
  onBootstrapLog: (cb: (line: string) => void) => void;
  onBootstrapError: (cb: (errMsg: string) => void) => void;
  onBootstrapComplete: (cb: () => void) => void;
  retryBootstrap: () => void;
}

  interface Window {
    tada: TadaAPI;
  }

} // end declare global

declare module "react" {
  interface CSSProperties {
    WebkitAppRegion?: "drag" | "no-drag";
  }
}

export {};
