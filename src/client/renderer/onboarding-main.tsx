import { createRoot } from "react-dom/client";
import { Onboarding } from "./components/onboarding/Onboarding";
import { setServerUrl } from "./api/client";

// Defer React render until the server URL is available so that
// useEffect hooks (e.g. getGoogleUser) can reach the Python server.
const root = document.getElementById("root")!;
const reactRoot = createRoot(root);
window.tada.onServerReady((data) => {
  setServerUrl(data.url);
  reactRoot.render(<Onboarding />);
});
