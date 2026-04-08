import { useAppContext } from "./context/AppContext";

export const FEATURE_FLAG_DEFAULTS: Record<string, boolean> = {
  moments: true,
  tabracadabra: true,
  tinker: false,
  connector_screen: true,
  connector_gmail: true,
  connector_calendar: true,
  connector_outlook_email: true,
  connector_outlook_calendar: true,
  connector_notifications: true,
  connector_filesystem: true,
  permission_screen: true,
  permission_notifications: true,
  permission_accessibility: true,
  permission_browser_cookies: true,
};

export function getFlag(
  flags: Record<string, boolean> | undefined,
  name: string,
): boolean {
  return flags?.[name] ?? FEATURE_FLAG_DEFAULTS[name] ?? true;
}

export function useFeatureFlag(name: string): boolean {
  const { state } = useAppContext();
  const flags = state.settings.feature_flags as Record<string, boolean> | undefined;
  return getFlag(flags, name);
}

export function useFeatureFlags(): Record<string, boolean> | undefined {
  const { state } = useAppContext();
  return state.settings.feature_flags as Record<string, boolean> | undefined;
}
