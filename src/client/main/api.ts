/** REST client — thin fetch wrapper for the Tada server. */

export { setServerUrl, getServerUrl } from "../shared/api-core";
import { request, getServerUrl } from "../shared/api-core";

export const getOnboardingStatus = () =>
  request("GET", "/api/onboarding/status");

// ── Moments ─────────────────────────────────────────────────
export const getMomentsTasks = () => request("GET", "/api/moments/tasks");
export const getMomentsResults = () => request("GET", "/api/moments/results");
export const getMomentResultHtml = (slug: string) =>
  fetch(`${getServerUrl()}/api/moments/results/${slug}/index.html`).then((r) => r.text());

// ── Recordings ───────────────────────────────────────────────
export const postAggregation = (data: unknown) =>
  request("POST", "/api/recordings/aggregation", data);
