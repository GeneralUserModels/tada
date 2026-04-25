/// <reference path="../../tada.d.ts" />
import React, { useEffect, useState } from "react";
import { PermissionModal } from "../modals/PermissionModal";
import { getFlag } from "../../featureFlags";
import { StepIndicator } from "./StepIndicator";
import { WelcomeStep } from "./steps/WelcomeStep";
import { WhatsNewStep } from "./steps/WhatsNewStep";
import { GoogleSignInStep } from "./steps/GoogleSignInStep";
import { ConnectorsStep } from "./steps/ConnectorsStep";
import { GettingReadyStep } from "./steps/GettingReadyStep";
import { TabracadabraStep } from "./steps/TabracadabraStep";
import { TadasStep } from "./steps/TadasStep";
import { MemexStep } from "./steps/MemexStep";
import { ModelsKeysStep } from "./steps/ModelsKeysStep";
import { LLM_MODELS, AGENT_MODELS, TINKER_MODELS } from "../shared/ModelDropdown";
import { LLM_ROWS, AGENT_ROWS, fanOut } from "../shared/AdvancedLLMSection";
import {
  startGoogleSignIn,
  getGoogleUser,
  startGoogleAuth,
  startOutlookAuth,
  checkNotificationsPermission,
  checkFilesystemPermission,
  checkBrowserCookiesPermission,
  getSettings,
  updateSettings,
  completeOnboarding,
  getOnboardingStatus,
  getServicesStatus,
  getGoogleConnectorStatus,
  getOutlookConnectorStatus,
} from "../../api/client";
import {
  pendingSteps,
  type OnboardingStep,
  type OnboardingState,
} from "../../../shared/onboardingSteps";

// Short titles + the icon each feature step renders at its top, so the
// What's New list previews the same glyph the user is about to see.
// Keyed by step id from ONBOARDING_STEPS.
const STEP_TITLES: Record<string, string> = {
  welcome: "Welcome to Tada",
  tabracadabra: "Tabracadabra",
  tadas: "Moments",
  memex: "Memex",
};

const STEP_DESCRIPTIONS: Record<string, string> = {
  tabracadabra: "Press Option + Tab to autocomplete or prompt from anywhere.",
  tadas: "Proactive mini-apps that run on their own schedule — answers waiting before you need to ask.",
  memex: "A personal wiki of your life — pages for the people, projects, and threads that keep coming up.",
};

const STEP_ICONS: Record<string, React.ReactNode> = {
  tabracadabra: (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
      <path d="M3 4.5h10M3 8h10M3 11.5h7" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
      <path d="M11.2 10.7 13.5 8.4l-2.3-2.3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  ),
  tadas: (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
      <path d="M8 1.5l1.6 3.4 3.7.5-2.7 2.6.7 3.7L8 9.9 4.7 11.7l.7-3.7L2.7 5.4l3.7-.5L8 1.5z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round"/>
    </svg>
  ),
  memex: (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
      <circle cx="8" cy="3.5" r="1.5" stroke="currentColor" strokeWidth="1.3"/>
      <circle cx="3.5" cy="8" r="1.5" stroke="currentColor" strokeWidth="1.3"/>
      <circle cx="12.5" cy="8" r="1.5" stroke="currentColor" strokeWidth="1.3"/>
      <circle cx="5.5" cy="13" r="1.5" stroke="currentColor" strokeWidth="1.3"/>
      <circle cx="10.5" cy="13" r="1.5" stroke="currentColor" strokeWidth="1.3"/>
      <path d="M6.5 4.5L5 6.5M9.5 4.5L11 6.5M3.5 9.5L5 11.5M12.5 9.5L11 11.5" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round"/>
    </svg>
  ),
};

const FALLBACK_ICON = (
  <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
    <path d="M4 8l3 3 5-6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
);

// Synthetic "What's new" step prepended for returning users.
const WHATS_NEW_STEP: OnboardingStep = { id: "whats_new", type: "intro" };

// ── Main Onboarding component ─────────────────────────────────

export function Onboarding({ serverReady = false }: { serverReady?: boolean }) {
  // Snapshot of which steps to walk the user through. Computed once after
  // initial API data lands, then held stable for the rest of the session so
  // the step list does not mutate under the user as they grant permissions.
  const [visibleSteps, setVisibleSteps] = useState<OnboardingStep[] | null>(null);
  const [step, setStep] = useState(0);
  const [permModal, setPermModal] = useState<{ name: string; onGranted: () => void } | null>(null);

  // Feature flags (loaded from server settings)
  const [ff, setFf] = useState<Record<string, boolean> | undefined>(undefined);
  const flag = (name: string) => getFlag(ff, name);

  // Google login state
  const [googleUser, setGoogleUser] = useState<{ name: string; email: string } | null>(null);
  const [googleLoading, setGoogleLoading] = useState(false);
  const [googleError, setGoogleError] = useState("");

  // Connector state
  const [screenGranted, setScreenGranted] = useState(false);
  const [calendarConnected, setCalendarConnected] = useState(false);
  const [gmailConnected, setGmailConnected] = useState(false);
  const [outlookConnected, setOutlookConnected] = useState(false);
  const [notifAvailable, setNotifAvailable] = useState(false);
  const [fsAvailable, setFsAvailable] = useState(false);
  const [notifEnabled, setNotifEnabled] = useState(false);
  const [fsEnabled, setFsEnabled] = useState(false);
  const [accessibilityGranted, setAccessibilityGranted] = useState(false);
  const [browserCookiesGranted, setBrowserCookiesGranted] = useState(false);
  const [micGranted, setMicGranted] = useState(false);
  const [sysAudioGranted, setSysAudioGranted] = useState(false);
  const [connectingGoogle, setConnectingGoogle] = useState<string | null>(null);
  const [connectingOutlook, setConnectingOutlook] = useState(false);

  // Load settings + onboarding status + saved Google user once the server is
  // reachable, then compute the visible step list. On first launch the window
  // opens before the server is up, so we wait for serverReady.
  useEffect(() => {
    if (!serverReady) return;
    if (visibleSteps !== null) return;

    let cancelled = false;
    (async () => {
      const [settings, status, user, services] = await Promise.all([
        getSettings().catch(() => ({} as Record<string, unknown>)),
        getOnboardingStatus().catch(() => ({
          complete: false,
          seen_steps: [] as string[],
          enabled_connectors: [] as string[],
        })),
        getGoogleUser().catch(() => null),
        getServicesStatus().catch(() => ({
          services_started: false,
          tabracadabra_ready: false,
          screen_frame_fresh: false,
        })),
      ]);
      if (cancelled) return;

      const flags = (settings as Record<string, unknown>).feature_flags as
        | Record<string, boolean>
        | undefined;
      setFf(flags);
      if (user) setGoogleUser(user);

      const state: OnboardingState = {
        seenSteps: status.seen_steps ?? [],
        featureFlags: flags,
        googleConnected: user != null,
        enabledConnectors: status.enabled_connectors ?? [],
        hasLlmApiKey:
          typeof (settings as Record<string, unknown>).default_llm_api_key === "string" &&
          ((settings as Record<string, unknown>).default_llm_api_key as string).length > 0,
        onboardingComplete: status.complete,
        // Treat "all three green" as "ready" — matches GettingReadyStep's
        // advance condition so returning users skip the spool wait entirely.
        servicesReady:
          services.services_started &&
          services.tabracadabra_ready &&
          services.screen_frame_fresh,
      };
      const pending = pendingSteps(state);

      // Nothing pending — shouldn't happen (main process already decided to
      // open the window) but close gracefully if it does.
      if (pending.length === 0) {
        window.tada.onboardingComplete();
        return;
      }

      // Returning user with new intro content gets a short framing page.
      const hasNewIntro = pending.some((s) => s.type === "intro");
      const nextSteps = status.complete && hasNewIntro
        ? [WHATS_NEW_STEP, ...pending]
        : pending;

      setVisibleSteps(nextSteps);
      setStep(0);
    })();

    return () => { cancelled = true; };
  }, [serverReady, visibleSteps]);

  // Model + API key state — defaults sourced from the shared model lists
  const [model, setModel] = useState(LLM_MODELS[0].value);
  const [agentModel, setAgentModel] = useState(AGENT_MODELS[0].value);
  const [tinkerModel, setTinkerModel] = useState(TINKER_MODELS[0].value);
  const [labelerKey, setLabelerKey] = useState("");
  const [agentKey, setAgentKey] = useState("");
  const [tinkerKey, setTinkerKey] = useState("");
  const [wandbKey, setWandbKey] = useState("");
  const [tinkerError, setTinkerError] = useState("");
  const [advancedValues, setAdvancedValues] = useState<Record<string, string>>({});

  const currentStep = visibleSteps ? visibleSteps[step] : null;
  const currentId = currentStep?.id;

  // Check screen + connector permissions whenever the user enters Connectors.
  useEffect(() => {
    if (currentId !== "connectors") return;
    async function checkScreen() {
      const status = await window.tada.checkScreenPermission();
      setScreenGranted(status === "granted");
    }
    checkScreen();

    async function checkAvailability() {
      const { granted: notif } = await checkNotificationsPermission();
      setNotifAvailable(notif);
      if (notif) setNotifEnabled(true);
      const { granted: fs } = await checkFilesystemPermission();
      setFsAvailable(fs);
      if (fs) setFsEnabled(true);
      // Per-folder TCC grants (Desktop/Documents/Downloads) are managed
      // inside SubPermissionRow now — no need to thread that state through
      // here. We re-check them once at submit time below.
      const accOk = await window.tada.checkConnectorPermission("accessibility");
      setAccessibilityGranted(accOk);
      // Use a non-invasive check on load. Real cookie/keychain access only runs
      // after explicit user action via the "Grant Access" modal.
      const cookiesOk = await window.tada.checkConnectorPermission("browser_cookies");
      setBrowserCookiesGranted(cookiesOk);
      const micOk = await window.tada.checkConnectorPermission("microphone");
      setMicGranted(micOk);
      const sysAudioOk = await window.tada.checkConnectorPermission("system_audio");
      setSysAudioGranted(sysAudioOk);
      // Rehydrate Google/Outlook connection state from persisted tokens so
      // restarting mid-onboarding doesn't lose progress.
      const g = await getGoogleConnectorStatus().catch(() => ({ connected: false }));
      if (g.connected) {
        setCalendarConnected(true);
        setGmailConnected(true);
      }
      const o = await getOutlookConnectorStatus().catch(() => ({ connected: false }));
      if (o.connected) setOutlookConnected(true);
    }
    checkAvailability();
  }, [currentId]);

  const handleGoogleLogin = async () => {
    setGoogleLoading(true);
    setGoogleError("");
    try {
      const result = await startGoogleSignIn();
      setGoogleUser(result);
    } catch (e) {
      console.error("[google signin]", e);
      setGoogleError("Sign in failed. Please try again.");
    } finally {
      setGoogleLoading(false);
    }
  };

  const handleConnectGoogle = async (svc: string) => {
    setConnectingGoogle(svc);
    try {
      await startGoogleAuth();
      // Python always requests both calendar and gmail scopes
      setCalendarConnected(true);
      setGmailConnected(true);
    } finally {
      setConnectingGoogle(null);
    }
  };

  const handleConnectOutlook = async () => {
    setConnectingOutlook(true);
    try {
      await startOutlookAuth();
      setOutlookConnected(true);
    } finally {
      setConnectingOutlook(false);
    }
  };

  const validateTinker = (val: string) => {
    if (val && !val.startsWith("tml-")) {
      setTinkerError('Tinker keys must start with "tml-"');
      return false;
    }
    setTinkerError("");
    return true;
  };

  const buildSettings = () => {
    const advanced: Record<string, string> = {};
    for (const [k, v] of Object.entries(advancedValues)) {
      if (v.trim()) advanced[k] = v.trim();
    }
    const selectedLlmModel = model || LLM_MODELS[0].value;
    const selectedAgentModel = agentModel || AGENT_MODELS[0].value;
    const trimmedAgentKey = agentKey.trim();
    const trimmedLabelerKey = labelerKey.trim();
    const settings: Record<string, unknown> = {
      ...fanOut(LLM_ROWS, "modelKey", selectedLlmModel),
      ...fanOut(AGENT_ROWS, "modelKey", selectedAgentModel),
      agent_model: selectedAgentModel,
      model: tinkerModel || undefined,
      default_llm_api_key: trimmedLabelerKey,
      ...fanOut(LLM_ROWS, "apiKeyKey", trimmedLabelerKey),
      ...(trimmedAgentKey ? { agent_api_key: trimmedAgentKey, ...fanOut(AGENT_ROWS, "apiKeyKey", trimmedAgentKey) } : {}),
      ...advanced,
    };
    if (tinkerKey.trim()) settings.tinker_api_key = tinkerKey.trim();
    if (wandbKey.trim()) settings.wandb_api_key = wandbKey.trim();
    return settings;
  };

  const saveSettings = () => updateSettings(buildSettings());

  // When the user advances past the connectors step, snapshot every connector
  // they've granted/connected and persist it via PUT /api/settings. This is
  // the single write path for enabled_connectors during onboarding — finalize
  // (called later by GettingReadyStep) is body-less and just flips the
  // onboarding_complete flag + kicks start_services.
  const handleConnectorsContinue = async () => {
    const enabled: string[] = [];
    if (screenGranted) enabled.push("screen");
    if (calendarConnected) enabled.push("calendar");
    if (gmailConnected) enabled.push("gmail");
    if (outlookConnected) {
      enabled.push("outlook_email");
      enabled.push("outlook_calendar");
    }
    if (notifAvailable) enabled.push("notifications");
    // Re-check per-folder TCC grants here since SubPermissionRow owns that
    // state. Any one folder being granted is enough to enable the connector —
    // the watcher tolerates the others being denied.
    const folderGrants = await Promise.all([
      window.tada.checkConnectorPermission("folder_desktop"),
      window.tada.checkConnectorPermission("folder_documents"),
      window.tada.checkConnectorPermission("folder_downloads"),
    ]);
    if (fsAvailable || folderGrants.some(Boolean)) {
      enabled.push("filesystem");
    }
    if (accessibilityGranted) enabled.push("accessibility");
    if (micGranted) enabled.push("microphone");
    if (sysAudioGranted) enabled.push("system_audio");

    try {
      await updateSettings({ enabled_connectors: enabled });
    } catch (e) {
      // Don't block advance on a transient settings write failure — finalize
      // will surface a "Try again" if start_services can't bring the screen
      // recorder up. Logging here so we have something in the console.
      console.error("[onboarding] failed to persist enabled_connectors", e);
    }
    advance(step);
  };

  const handleSubmit = async () => {
    // By the time we reach the final tutorial page, everything heavy has
    // already been persisted: connectors via PUT /api/settings on the
    // connectors step, model + API keys via ModelsKeysStep.onFinish, and
    // onboarding_complete via /api/onboarding/finalize on getting_ready. All
    // that's left is recording which intro pages the user actually saw.
    const seenIntros = (visibleSteps ?? [])
      .filter((s) => s.type === "intro" && s.id !== WHATS_NEW_STEP.id)
      .map((s) => s.id);

    await completeOnboarding(seenIntros);
    window.tada.onboardingComplete();
  };

  const advance = (from: number) => {
    if (!visibleSteps) return;
    if (from >= visibleSteps.length - 1) {
      handleSubmit();
    } else {
      setStep(from + 1);
    }
  };
  const goBack = (from: number) => setStep(Math.max(0, from - 1));
  const isFinal = (from: number) =>
    visibleSteps != null && from >= visibleSteps.length - 1;

  const openPermissionModal = (name: string, onGranted: () => void) => {
    setPermModal({ name, onGranted });
  };

  // Before the step snapshot is ready, render the shell that matches whatever
  // the first real step is going to be — Welcome for first-timers, What's New
  // for returning users — so the handshake doesn't flash the wrong screen.
  // Main process passes the hint via URL query param.
  if (!visibleSteps) {
    const mode = new URLSearchParams(window.location.search).get("mode");
    return (
      <>
        <div className="drag-topbar" />
        <div className="wrapper">
          {mode === "returning" ? (
            <WhatsNewStep newFeatures={[]} onContinue={() => {}} loading />
          ) : (
            <WelcomeStep onStart={() => {}} serverReady={false} />
          )}
        </div>
      </>
    );
  }

  return (
    <>
    <div className="drag-topbar" />
    <div className="wrapper">
      {permModal && (
        <PermissionModal
          connectorName={permModal.name}
          onClose={() => setPermModal(null)}
          onGranted={permModal.onGranted}
          checkPermission={
            permModal.name === "browser_cookies"
              ? async () => (await checkBrowserCookiesPermission()).granted
              : undefined
          }
          skipConnectorUpdate
          dismissDelay={700}
          cardStyle={{ maxWidth: 320 }}
          useClassButtons
        />
      )}

      <StepIndicator current={step} total={visibleSteps.length} />

      {currentId === "welcome" && (
        <WelcomeStep onStart={() => advance(step)} serverReady={serverReady} />
      )}

      {currentId === "whats_new" && (
        <WhatsNewStep
          newFeatures={visibleSteps
            .filter((s) => s.type === "intro" && s.id !== WHATS_NEW_STEP.id)
            .map((s) => ({
              id: s.id,
              title: STEP_TITLES[s.id] ?? s.id,
              description: STEP_DESCRIPTIONS[s.id] ?? "",
              icon: STEP_ICONS[s.id] ?? FALLBACK_ICON,
            }))}
          onContinue={() => advance(step)}
        />
      )}

      {currentId === "google_signin" && (
        <GoogleSignInStep
          googleUser={googleUser}
          googleLoading={googleLoading}
          googleError={googleError}
          onBack={() => goBack(step)}
          onContinue={() => advance(step)}
          onGoogleLogin={handleGoogleLogin}
        />
      )}

      {currentId === "connectors" && (
        <ConnectorsStep
          flag={flag}
          screenGranted={screenGranted}
          calendarConnected={calendarConnected}
          outlookConnected={outlookConnected}
          notifAvailable={notifAvailable}
          fsAvailable={fsAvailable}
          accessibilityGranted={accessibilityGranted}
          browserCookiesGranted={browserCookiesGranted}
          connectingGoogle={connectingGoogle}
          connectingOutlook={connectingOutlook}
          onBack={() => goBack(step)}
          onContinue={handleConnectorsContinue}
          onOpenPermissionModal={openPermissionModal}
          onConnectGoogle={handleConnectGoogle}
          onConnectOutlook={handleConnectOutlook}
          setScreenGranted={setScreenGranted}
          setNotifAvailable={setNotifAvailable}
          setNotifEnabled={setNotifEnabled}
          setFsAvailable={setFsAvailable}
          setFsEnabled={setFsEnabled}
          setBrowserCookiesGranted={setBrowserCookiesGranted}
          setAccessibilityGranted={setAccessibilityGranted}
          micGranted={micGranted}
          setMicGranted={setMicGranted}
          sysAudioGranted={sysAudioGranted}
          setSysAudioGranted={setSysAudioGranted}
        />
      )}

      {currentId === "models_keys" && (
        <ModelsKeysStep
          flag={flag}
          model={model}
          agentModel={agentModel}
          tinkerModel={tinkerModel}
          labelerKey={labelerKey}
          agentKey={agentKey}
          tinkerKey={tinkerKey}
          wandbKey={wandbKey}
          tinkerError={tinkerError}
          advancedValues={advancedValues}
          setModel={setModel}
          setAgentModel={setAgentModel}
          setTinkerModel={setTinkerModel}
          setLabelerKey={setLabelerKey}
          setAgentKey={setAgentKey}
          setTinkerKey={setTinkerKey}
          setWandbKey={setWandbKey}
          setAdvancedValues={setAdvancedValues}
          validateTinker={validateTinker}
          onBack={() => goBack(step)}
          onFinish={() => { saveSettings(); advance(step); }}
        />
      )}

      {currentId === "getting_ready" && (
        <GettingReadyStep onContinue={() => advance(step)} />
      )}

      {currentId === "tabracadabra" && (
        <TabracadabraStep
          onBack={() => goBack(step)}
          onContinue={() => advance(step)}
          isFinal={isFinal(step)}
        />
      )}

      {currentId === "tadas" && (
        <TadasStep
          onBack={() => goBack(step)}
          onContinue={() => advance(step)}
          isFinal={isFinal(step)}
        />
      )}

      {currentId === "memex" && (
        <MemexStep
          onBack={() => goBack(step)}
          onContinue={() => advance(step)}
        />
      )}
    </div>
    </>
  );
}
