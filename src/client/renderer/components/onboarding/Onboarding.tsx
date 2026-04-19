/// <reference path="../../tada.d.ts" />
import React, { useEffect, useState } from "react";
import { PermissionModal } from "../modals/PermissionModal";
import { getFlag } from "../../featureFlags";
import { StepIndicator } from "./StepIndicator";
import { WelcomeStep } from "./steps/WelcomeStep";
import { GoogleSignInStep } from "./steps/GoogleSignInStep";
import { ConnectorsStep } from "./steps/ConnectorsStep";
import { TabracadabraStep } from "./steps/TabracadabraStep";
import { ModelsKeysStep } from "./steps/ModelsKeysStep";
import { LLM_MODELS, AGENT_MODELS, TINKER_MODELS } from "../shared/ModelDropdown";
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
} from "../../api/client";

// ── Main Onboarding component ─────────────────────────────────

export function Onboarding({ serverReady = false }: { serverReady?: boolean }) {
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

  // Load feature flags + restore saved Google user once the server is reachable.
  // On first launch the onboarding window opens before the server is up, so we
  // wait for serverReady rather than firing on mount and failing silently.
  useEffect(() => {
    if (!serverReady) return;

    getSettings()
      .then((s) => setFf((s as Record<string, unknown>).feature_flags as Record<string, boolean> | undefined))
      .catch(() => {});

    getGoogleUser().then(user => {
      if (user) {
        setGoogleUser(user);
        setStep(2);
      }
    }).catch(() => {});
  }, [serverReady]);

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

  // Check screen permission when entering step 2
  useEffect(() => {
    if (step !== 2) return;
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
    }
    checkAvailability();
  }, [step]);

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
    const settings: Record<string, unknown> = {
      // Labeling LM fans out to labeling-type consumers.
      reward_llm: selectedLlmModel,
      label_model: selectedLlmModel,
      filter_model: selectedLlmModel,
      tabracadabra_model: selectedLlmModel,
      // Agent LM fans out to agentic consumers (Tada, Pensieve, Seeker).
      agent_model: selectedAgentModel,
      moments_agent_model: selectedAgentModel,
      memory_agent_model: selectedAgentModel,
      seeker_model: selectedAgentModel,
      model: tinkerModel || undefined,
      default_llm_api_key: labelerKey.trim(),
      ...advanced,
    };
    if (trimmedAgentKey) {
      settings.agent_api_key = trimmedAgentKey;
      settings.moments_agent_api_key = trimmedAgentKey;
      settings.memory_agent_api_key = trimmedAgentKey;
      settings.seeker_api_key = trimmedAgentKey;
    }
    if (tinkerKey.trim()) settings.tinker_api_key = tinkerKey.trim();
    if (wandbKey.trim()) settings.wandb_api_key = wandbKey.trim();
    return settings;
  };

  const saveSettings = () => updateSettings(buildSettings());

  const handleSubmit = async () => {
    await saveSettings();
    await completeOnboarding();
    window.tada.onboardingComplete();
  };

  const openPermissionModal = (name: string, onGranted: () => void) => {
    setPermModal({ name, onGranted });
  };

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

      <StepIndicator current={step} total={5} />

      {step === 0 && <WelcomeStep onStart={() => setStep(1)} serverReady={serverReady} />}

      {step === 1 && (
        <GoogleSignInStep
          googleUser={googleUser}
          googleLoading={googleLoading}
          googleError={googleError}
          onBack={() => setStep(0)}
          onContinue={() => setStep(2)}
          onGoogleLogin={handleGoogleLogin}
        />
      )}

      {step === 2 && (
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
          onBack={() => setStep(1)}
          onContinue={() => setStep(3)}
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

      {step === 3 && (
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
          onBack={() => setStep(2)}
          onFinish={() => { saveSettings(); setStep(4); }}
        />
      )}

      {step === 4 && (
        <TabracadabraStep
          onBack={() => setStep(3)}
          onContinue={handleSubmit}
        />
      )}
    </div>
    </>
  );
}
