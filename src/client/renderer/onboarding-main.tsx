import React, { useState, useEffect } from "react";
import { createRoot } from "react-dom/client";
import { Onboarding } from "./components/onboarding/Onboarding";
import { setServerUrl } from "./api/client";

// Render React immediately so the Welcome step appears without waiting
// for the Python server. Server-dependent work inside <Onboarding> is
// gated on the serverReady prop, which flips once onServerReady fires.
const root = document.getElementById("root")!;
const reactRoot = createRoot(root);

function OnboardingRoot() {
  const [ready, setReady] = useState(false);

  useEffect(() => {
    window.tada.onServerReady(({ url }) => {
      setServerUrl(url);
      setReady(true);
    });
  }, []);

  return <Onboarding serverReady={ready} />;
}

reactRoot.render(<OnboardingRoot />);
