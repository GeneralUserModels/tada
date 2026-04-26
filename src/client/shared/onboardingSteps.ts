/**
 * Canonical onboarding step list + completion predicates.
 *
 * Used by the Electron main process (to decide whether to open the onboarding
 * window at startup) and by the renderer (to decide which steps to render).
 * Keeping both call sites on the same data is what makes "resume onboarding
 * on update" — showing only the new steps after an app upgrade — possible.
 *
 * Two kinds of steps:
 *   - "intro": pure informational pages. Only way to know the user has seen
 *     one is an explicit persisted marker (`seenSteps`).
 *   - "config": steps whose real work lives elsewhere (OAuth, API keys, OS
 *     permissions). Completion is derived from that state directly, so the
 *     step is automatically skipped once the state says it's done.
 */

export type StepType = "intro" | "config";

export type OnboardingStep = {
  id: string;
  type: StepType;
  flag?: string;
};

export const ONBOARDING_STEPS: readonly OnboardingStep[] = [
  { id: "welcome",       type: "intro" },
  { id: "google_signin", type: "config" },
  { id: "connectors",    type: "config" },
  { id: "models_keys",   type: "config" },
  { id: "tabracadabra",  type: "intro" },
  { id: "chat",          type: "intro" },
  { id: "tadas",         type: "intro", flag: "moments" },
  { id: "memex",         type: "intro", flag: "memory"  },
];

export type OnboardingState = {
  seenSteps: string[];
  featureFlags?: Record<string, boolean>;
  googleConnected: boolean;
  enabledConnectors: string[];
  hasLlmApiKey: boolean;
  onboardingComplete: boolean;
};

export function isStepEnabled(
  step: OnboardingStep,
  flags: Record<string, boolean> | undefined,
): boolean {
  if (!step.flag) return true;
  return flags?.[step.flag] === true;
}

export function isStepDone(step: OnboardingStep, state: OnboardingState): boolean {
  if (step.type === "intro") {
    // "welcome" is a first-time greeting; returning users get WhatsNewStep instead.
    if (step.id === "welcome" && state.onboardingComplete) return true;
    return state.seenSteps.includes(step.id);
  }
  switch (step.id) {
    case "google_signin":
      return state.googleConnected;
    case "connectors":
      return (
        state.enabledConnectors.includes("screen") &&
        state.enabledConnectors.includes("accessibility")
      );
    case "models_keys":
      return state.hasLlmApiKey;
    default:
      return false;
  }
}

export function pendingSteps(state: OnboardingState): OnboardingStep[] {
  return ONBOARDING_STEPS.filter(
    (s) => isStepEnabled(s, state.featureFlags) && !isStepDone(s, state),
  );
}
