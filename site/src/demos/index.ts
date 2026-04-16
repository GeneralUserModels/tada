export type { Demo, DemoStep, DemoTheme } from "./types";

import { overleafDemo } from "./overleaf";
import { mailDemo } from "./mail";
import { slackDemo } from "./slack";

export const DEMOS: readonly import("./types").Demo[] = [
  overleafDemo,
  mailDemo,
  slackDemo,
];
