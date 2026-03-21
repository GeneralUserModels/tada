/** Global type for the powernap context bridge exposed by preload.ts */

interface StatusData {
  training_active: boolean;
  labels_processed: number;
  untrained_batches: number;
  step_count: number;
  inference_buffer_size: number;
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
  configured: boolean;
  error?: string | null;
}

interface ConnectorPermissionInfo {
  title: string;
  body: string;
  steps: string[];
  fixUrl: string;
  hasRequest: boolean;
}

interface PowerNapAPI {
  // Control
  startRecording: () => Promise<unknown>;
  stopRecording: () => Promise<unknown>;
  startTraining: () => Promise<unknown>;
  stopTraining: () => Promise<unknown>;
  startInference: () => Promise<unknown>;
  stopInference: () => Promise<unknown>;
  requestPrediction: () => Promise<unknown>;

  // Status / Settings
  getStatus: () => Promise<StatusData>;
  getSettings: () => Promise<Record<string, unknown>>;
  updateSettings: (data: Record<string, unknown>) => Promise<unknown>;
  getTrainingHistory: () => Promise<TrainingStepData[]>;

  // Dashboard event listeners
  onServerReady: (cb: () => void) => void;
  onStatusUpdate: (cb: (data: StatusData) => void) => void;
  onPrediction: (cb: (data: PredictionData) => void) => void;
  onScore: (cb: (data: ScoreData) => void) => void;
  onElboScore: (cb: (data: ElboScoreData) => void) => void;
  onTrainingStep: (cb: (data: TrainingStepData) => void) => void;
  onLabel: (cb: (data: LabelData) => void) => void;
  onPredictionRequested: (cb: () => void) => void;

  // Overlay-specific
  onOverlayPrediction: (cb: (data: PredictionData) => void) => void;
  onOverlayWaiting: (cb: () => void) => void;
  onOverlayFlushing: (cb: () => void) => void;
  onOverlaySleepwalk: (cb: () => void) => void;
  resizeOverlay: (height: number) => void;

  // Connectors
  getConnectorStatus: () => Promise<Record<string, ConnectorInfo>>;
  connectorConnectGoogle: (scope?: string) => Promise<boolean>;
  connectorDisconnectGoogle: () => Promise<unknown>;
  connectorConnectOutlook: () => Promise<boolean>;
  connectorDisconnectOutlook: () => Promise<unknown>;
  updateConnector: (name: string, enabled: boolean) => Promise<unknown>;
  openFdaSettings: (name?: string) => Promise<unknown>;
  getConnectorPermissionInfo: (name: string) => Promise<ConnectorPermissionInfo | null>;
  checkConnectorPermission: (name: string) => Promise<boolean>;
  requestConnectorPermission: (name: string) => Promise<boolean>;

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

  // Onboarding
  googleLogin: () => Promise<{ name: string; email: string }>;
  connectGoogle: (scope: string) => Promise<boolean>;
  connectOutlook: () => Promise<boolean>;
  checkNotifications: () => Promise<boolean>;
  checkFilesystem: () => Promise<boolean>;
  submitOnboarding: (data: Record<string, unknown>) => void;
}

declare global {
  interface Window {
    powernap: PowerNapAPI;
  }
}

export {};
