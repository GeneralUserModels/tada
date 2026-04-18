import type { ReactNode } from "react";

export interface DemoTheme {
  app: string;
  icon: string;
  fontFamily: string;
  fontSize: string;
  bg: string;
  headerBg: string;
  headerText: string;
  textColor: string;
  cursorColor: string;
}

export type DemoStep =
  | {
      kind: "user";
      text: string;
      pauseAfter?: number;
    }
  | {
      kind: "assistant";
      text: string;
      trigger: "autocomplete" | "prompt";
      pauseAfter?: number;
    }
  | {
      kind: "delete";
      count?: number;
      from?: "start" | "end" | "middle";
      start?: number;
      matchText?: string;
      pauseAfter?: number;
    };

export interface Demo {
  steps: DemoStep[];
  theme: DemoTheme;
  topChrome: ReactNode;
  bottomChrome?: ReactNode;
}
