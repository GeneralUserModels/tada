import { useAppContext } from "./context/AppContext";

export function getFlag(
  flags: Record<string, boolean> | undefined,
  name: string,
): boolean {
  // Frontend does not define fallback defaults; backend is source-of-truth.
  return flags?.[name] === true;
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
