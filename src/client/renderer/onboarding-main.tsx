import { createRoot } from "react-dom/client";
import { Onboarding } from "./components/onboarding/Onboarding";
import { setServerUrl } from "./api/client";

// Register before React renders so the once-listener is set up before
// did-finish-load fires on the main process side.
window.powernap.onServerReady((data) => setServerUrl(data.url));

const root = document.getElementById("root")!;
createRoot(root).render(<Onboarding />);
