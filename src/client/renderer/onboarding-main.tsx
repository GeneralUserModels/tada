import React from "react";
import { createRoot } from "react-dom/client";
import { Onboarding } from "./components/onboarding/Onboarding";
import { setServerUrl } from "./api/client";

// Defer React render until the server URL is available so that
// useEffect hooks (e.g. getGoogleUser) can reach the Python server.
const root = document.getElementById("root")!;
const reactRoot = createRoot(root);

async function bootstrapOnboarding() {
  try {
    const url = await window.tada.getServerUrl();
    if (url) setServerUrl(url);
  } catch {
    console.warn("[onboarding] failed to fetch server URL");
  } finally {
    reactRoot.render(<Onboarding />);
  }
}

void bootstrapOnboarding();
