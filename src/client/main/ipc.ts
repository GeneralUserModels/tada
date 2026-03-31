/** IPC channel definitions shared between main and renderer processes. */

export const IPC = {
  // Main -> Dashboard
  SERVER_READY: "server:ready",
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

  // Onboarding — screen permission (Electron-only) + completion signal
  ONBOARDING_CHECK_SCREEN_PERMISSION: "onboarding:check-screen-permission",
  ONBOARDING_OPEN_SCREEN_SETTINGS: "onboarding:open-screen-settings",
  ONBOARDING_REQUEST_SCREEN_PERMISSION: "onboarding:request-screen-permission",
  ONBOARDING_OPEN_FDA_SETTINGS: "onboarding:open-fda-settings",
  ONBOARDING_COMPLETE: "onboarding:complete",

  // Connectors (OS-level permissions only — data fetching goes direct to Python)
  CONNECTOR_OPEN_FDA_SETTINGS: "connector:open-fda-settings",
  CONNECTOR_GET_PERMISSION_INFO: "connector:get-permission-info",
  CONNECTOR_REQUEST_PERMISSION: "connector:request-permission",
  CONNECTOR_CHECK_PERMISSION: "connector:check-permission",

  // Moments (Ta-Da)
  MOMENTS_GET_TASKS: "moments:get-tasks",
  MOMENTS_GET_RESULTS: "moments:get-results",
  MOMENTS_GET_RESULT_HTML: "moments:get-result-html",
  MOMENT_COMPLETED: "moment:completed",

  // Auto-update
  UPDATE_DOWNLOADED: "update:downloaded",
  UPDATE_ERROR: "update:error",
  UPDATE_INSTALL_NOW: "update:install-now",
  UPDATE_INSTALL_ON_QUIT: "update:install-on-quit",
  UPDATE_DISMISS: "update:dismiss",
  UPDATE_CHECK: "update:check",
} as const;
