/** Spawns the recording bridge as a child process, reads stdout, POSTs to server. */

import { spawn, ChildProcess } from "child_process";
import * as path from "path";
import * as readline from "readline";
import { postAggregation } from "./api";
import { isDev, getDataDir, getPythonPath, getPythonSrcDir } from "./paths";

let proc: ChildProcess | null = null;

export function startRecording(fps = 5, bufferSeconds = 12): void {
  if (proc) return;

  const pythonPath = getPythonPath();

  const configPath = path.join(getDataDir(), "powernap-config.json");

  if (isDev()) {
    // Dev mode: use uv run from repo root
    const projectRoot = getDataDir();
    proc = spawn("uv", [
      "run", "python", "-m", "connectors.screen.napsack",
      "--fps", String(fps),
      "--buffer-seconds", String(bufferSeconds),
    ], {
      stdio: ["pipe", "pipe", "pipe"],
      cwd: projectRoot,
      env: { ...process.env, POWERNAP_CONFIG_PATH: configPath },
    });
  } else {
    // Packaged mode: use venv python directly with PYTHONPATH
    proc = spawn(pythonPath, [
      "-m", "connectors.screen.napsack",
      "--fps", String(fps),
      "--buffer-seconds", String(bufferSeconds),
    ], {
      stdio: ["pipe", "pipe", "pipe"],
      env: {
        ...process.env,
        PYTHONPATH: getPythonSrcDir(),
        POWERNAP_CONFIG_PATH: configPath,
      },
    });
  }

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
