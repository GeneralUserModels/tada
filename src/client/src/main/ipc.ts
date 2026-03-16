/** IPC channel definitions shared between main and renderer processes. */

export const IPC = {
  // Dashboard -> Main
  CONTROL_RECORDING_START: "control:recording:start",
  CONTROL_RECORDING_STOP: "control:recording:stop",
  CONTROL_TRAINING_START: "control:training:start",
  CONTROL_TRAINING_STOP: "control:training:stop",
  CONTROL_INFERENCE_START: "control:inference:start",
  CONTROL_INFERENCE_STOP: "control:inference:stop",
  REQUEST_PREDICTION: "request:prediction",
  GET_STATUS: "get:status",
  GET_SETTINGS: "get:settings",
  UPDATE_SETTINGS: "update:settings",
  GET_TRAINING_HISTORY: "get:training:history",

  // Main -> Dashboard
  SERVER_READY: "server:ready",
  STATUS_UPDATE: "status:update",
  PREDICTION: "prediction",
  SCORE: "score",
  ELBO_SCORE: "elbo:score",
  TRAINING_STEP: "training:step",
  LABEL: "label",

  PREDICTION_REQUESTED: "prediction:requested",

  // Main -> Overlay
  OVERLAY_PREDICTION: "overlay:prediction",
  OVERLAY_WAITING: "overlay:waiting",
  OVERLAY_FLUSHING: "overlay:flushing",

  // Bootstrap (main -> setup window)
  BOOTSTRAP_PROGRESS: "bootstrap:progress",
  BOOTSTRAP_LOG: "bootstrap:log",
  BOOTSTRAP_ERROR: "bootstrap:error",
  BOOTSTRAP_COMPLETE: "bootstrap:complete",

  // Bootstrap (setup window -> main)
  BOOTSTRAP_RETRY: "bootstrap:retry",

  // Onboarding
  ONBOARDING_SUBMIT: "onboarding:submit",
  ONBOARDING_CHECK_SCREEN_PERMISSION: "onboarding:check-screen-permission",
  ONBOARDING_OPEN_SCREEN_SETTINGS: "onboarding:open-screen-settings",
  ONBOARDING_REQUEST_SCREEN_PERMISSION: "onboarding:request-screen-permission",
  ONBOARDING_GOOGLE_LOGIN: "onboarding:google-login",

  // Connectors (onboarding)
  ONBOARDING_CONNECT_GOOGLE: "onboarding:connect-google",
  ONBOARDING_CONNECT_OUTLOOK: "onboarding:connect-outlook",
  ONBOARDING_CHECK_NOTIFICATIONS: "onboarding:check-notifications",
  ONBOARDING_CHECK_FILESYSTEM: "onboarding:check-filesystem",

  // Connectors (dashboard)
  CONNECTOR_STATUS: "connector:status",
  CONNECTOR_CONNECT_GOOGLE: "connector:connect-google",
  CONNECTOR_DISCONNECT_GOOGLE: "connector:disconnect-google",
  CONNECTOR_CONNECT_OUTLOOK: "connector:connect-outlook",
  CONNECTOR_DISCONNECT_OUTLOOK: "connector:disconnect-outlook",
  CONNECTOR_UPDATE: "connector:update",

  // Auto-update
  UPDATE_AVAILABLE: "update:available",
  UPDATE_ERROR: "update:error",
  UPDATE_OPEN_RELEASE: "update:open-release",
  UPDATE_CHECK: "update:check",
} as const;
