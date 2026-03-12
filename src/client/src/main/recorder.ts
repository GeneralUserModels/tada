/** Spawns the recording bridge as a child process, reads stdout, POSTs to server. */

import { spawn, ChildProcess } from "child_process";
import * as path from "path";
import * as readline from "readline";
import { postAggregation } from "./api";

let proc: ChildProcess | null = null;

export function startRecording(fps = 5, bufferSeconds = 12): void {
  if (proc) return;

  const projectRoot = path.resolve(__dirname, "..", "..", "..", "..");
  const pythonPath = path.join(projectRoot, ".venv", "bin", "python");

  proc = spawn(pythonPath, ["-m", "connectors.screen.napsack", "--fps", String(fps), "--buffer-seconds", String(bufferSeconds)], {
    stdio: ["pipe", "pipe", "pipe"],
  });

  const rl = readline.createInterface({ input: proc.stdout! });

  rl.on("line", async (line: string) => {
    const trimmed = line.trim();
    if (!trimmed || !trimmed.startsWith("{")) return;
    try {
      const data = JSON.parse(trimmed);
      await postAggregation(data);
    } catch (err) {
      console.error("[recorder] failed to POST aggregation:", err);
    }
  });

  proc.stderr?.on("data", (chunk: Buffer) => {
    // Relay bridge stderr to console for debugging
    process.stderr.write(`[bridge] ${chunk}`);
  });

  proc.on("exit", (code: number | null) => {
    console.log(`[recorder] bridge exited with code ${code}`);
    proc = null;
  });

  console.log("[recorder] bridge started");
}

export function stopRecording(): void {
  if (!proc) return;
  proc.kill("SIGTERM");
  proc = null;
  console.log("[recorder] bridge stopped");
}

export function isRecording(): boolean {
  return proc !== null;
}
