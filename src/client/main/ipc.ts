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
  ONBOARDING_OPEN_FDA_SETTINGS: "onboarding:open-fda-settings",

  // Connectors (dashboard — OAuth and OS-level only)
  CONNECTOR_STATUS: "connector:status",
  CONNECTOR_STATUS_UPDATE: "connector:status-update",
  CONNECTOR_OPEN_FDA_SETTINGS: "connector:open-fda-settings",
  CONNECTOR_GET_PERMISSION_INFO: "connector:get-permission-info",
  CONNECTOR_REQUEST_PERMISSION: "connector:request-permission",
  CONNECTOR_CONNECT_GOOGLE: "connector:connect-google",
  CONNECTOR_DISCONNECT_GOOGLE: "connector:disconnect-google",
  CONNECTOR_CONNECT_OUTLOOK: "connector:connect-outlook",
  CONNECTOR_DISCONNECT_OUTLOOK: "connector:disconnect-outlook",

  // Auto-update
  UPDATE_DOWNLOADED: "update:downloaded",
  UPDATE_ERROR: "update:error",
  UPDATE_INSTALL_NOW: "update:install-now",
  UPDATE_INSTALL_ON_QUIT: "update:install-on-quit",
  UPDATE_DISMISS: "update:dismiss",
  UPDATE_CHECK: "update:check",
} as const;
