/** IPC channel definitions shared between main and renderer processes. */

export const IPC = {
  // Main -> Dashboard
  SERVER_READY: "server:ready",

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

  // Moments (Tada)
  MOMENTS_GET_TASKS: "moments:get-tasks",
  MOMENTS_GET_RESULTS: "moments:get-results",
  GET_SERVER_URL: "get:server-url",
  MOMENT_COMPLETED: "moment:completed",

  // Update check
  UPDATE_AVAILABLE: "update:available",
  UPDATE_PROGRESS: "update:progress",
  UPDATE_DOWNLOADED: "update:downloaded",
  UPDATE_ERROR: "update:error",
  UPDATE_DISMISS: "update:dismiss",
  UPDATE_CHECK: "update:check",
  UPDATE_INSTALL: "update:install",

  // External URLs
  OPEN_EXTERNAL_URL: "external:open-url",
} as const;
