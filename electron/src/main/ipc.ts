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
  OVERLAY_SLEEPWALK: "overlay:sleepwalk",
} as const;
