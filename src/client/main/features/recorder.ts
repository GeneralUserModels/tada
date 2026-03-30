/** Spawns the recording bridge as a child process, reads stdout, POSTs to server. */

import { ChildProcess } from "child_process";

let proc: ChildProcess | null = null;

export function stopRecording(): void {
  if (!proc) return;
  proc.kill("SIGTERM");
  proc = null;
  console.log("[recorder] bridge stopped");
}
