/** REST client — thin fetch wrapper for the PowerNap server. */

export { setServerUrl, getServerUrl } from "../shared/api-core";
import { request } from "../shared/api-core";

export const requestPrediction = () =>
  request("POST", "/api/user_models/prediction");

export const getOnboardingStatus = () =>
  request("GET", "/api/onboarding/status");
