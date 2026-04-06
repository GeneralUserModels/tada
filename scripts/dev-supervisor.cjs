#!/usr/bin/env node
/* Dev supervisor: one owner for Vite + server + Electron. */

const path = require("path");
const os = require("os");
const net = require("net");
const { spawn } = require("child_process");

const isWin = process.platform === "win32";
const repoRoot = path.resolve(__dirname, "..");
const children = new Map();
let shuttingDown = false;
let electronStarted = false;
let buildProc = null;
let rendererReady = false;
let serverReady = false;

function findFreePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.listen(0, "127.0.0.1", () => {
      const address = srv.address();
      const port = typeof address === "object" && address ? address.port : null;
      srv.close(() => {
        if (typeof port === "number") resolve(port);
        else reject(new Error("Failed to find free port"));
      });
    });
    srv.on("error", reject);
  });
}

function spawnManaged(name, cmd, args, options = {}) {
  const child = spawn(cmd, args, {
    stdio: "inherit",
    env: process.env,
    ...options,
    detached: Boolean(options.detached),
  });
  children.set(name, child);
  child.on("exit", (code, signal) => {
    children.delete(name);
    if (shuttingDown) return;
    if (name === "waitOnRenderer" || name === "waitOnServer") {
      if (code !== 0) {
        console.log(`[dev-supervisor] ${name} failed (${signal || code}); shutting down`);
        shutdown(1);
      }
      return;
    }
    if (name === "vite" || name === "electron" || name === "server") {
      console.log(`[dev-supervisor] ${name} exited (${signal || code}); shutting down`);
      shutdown(name === "electron" ? (code || 0) : 1);
    }
  });
  return child;
}

function killTree(child, signal = "SIGTERM") {
  if (!child || child.killed) return;
  try {
    if (!isWin && child.pid && child.spawnargs && child.spawnargs[0] === "uv") {
      // Server is spawned in its own process group; kill the full group.
      process.kill(-child.pid, signal);
    } else {
      child.kill(signal);
    }
  } catch {
    // Best-effort cleanup.
  }
}

function shutdown(exitCode = 0) {
  if (shuttingDown) return;
  shuttingDown = true;

  killTree(buildProc, "SIGTERM");
  killTree(children.get("electron"), "SIGTERM");
  killTree(children.get("waitOnRenderer"), "SIGTERM");
  killTree(children.get("waitOnServer"), "SIGTERM");
  killTree(children.get("server"), "SIGTERM");
  killTree(children.get("vite"), "SIGTERM");

  setTimeout(() => {
    killTree(buildProc, "SIGKILL");
    killTree(children.get("electron"), "SIGKILL");
    killTree(children.get("waitOnRenderer"), "SIGKILL");
    killTree(children.get("waitOnServer"), "SIGKILL");
    killTree(children.get("server"), "SIGKILL");
    killTree(children.get("vite"), "SIGKILL");
    process.exit(exitCode);
  }, 2000);
}

function maybeStartElectron(serverUrl) {
  if (shuttingDown || electronStarted || !rendererReady || !serverReady) return;
  electronStarted = true;
  console.log(`[dev-supervisor] starting Electron (server=${serverUrl})...`);
  spawnManaged("electron", "npx", ["electron", "dist/main/index.js"], {
    env: { ...process.env, POWERNAP_SERVER_URL: serverUrl },
  });
}

process.on("SIGINT", () => shutdown(130));
process.on("SIGTERM", () => shutdown(143));
process.on("SIGHUP", () => shutdown(129));

(async () => {
  console.log("[dev-supervisor] building main process...");
  const build = spawn("npm", ["run", "build:main"], { stdio: "inherit", env: process.env });
  buildProc = build;
  const buildCode = await new Promise((resolve) => build.on("exit", resolve));
  buildProc = null;
  if (buildCode !== 0) {
    process.exit(buildCode || 1);
    return;
  }

  const port = await findFreePort();
  const serverUrl = `http://127.0.0.1:${port}`;

  console.log("[dev-supervisor] starting Vite...");
  spawnManaged("vite", "npx", ["vite"]);

  console.log(`[dev-supervisor] starting server on ${serverUrl} ...`);
  const tokenBase = path.join(os.homedir(), ".config", "powernap");
  spawnManaged("server", "uv", [
    "run", "python", "-m", "server",
    "--port", String(port),
    "--log-dir", path.join(repoRoot, "logs"),
    "--google-token-path", path.join(tokenBase, "google-token.json"),
    "--outlook-token-path", path.join(tokenBase, "outlook-token.json"),
    "--save-recordings",
    "--resume-from-checkpoint", "auto",
    "--log-to-wandb",
  ], {
    detached: !isWin,
    cwd: repoRoot,
    env: { ...process.env, POWERNAP_CONFIG_PATH: path.join(repoRoot, "powernap-config.json") },
  });

  console.log("[dev-supervisor] waiting for renderer at http://localhost:5173 ...");
  const waitOnRenderer = spawnManaged("waitOnRenderer", "npx", ["wait-on", "http://localhost:5173"]);
  waitOnRenderer.on("exit", (code) => {
    if (code === 0 && !shuttingDown) {
      rendererReady = true;
      maybeStartElectron(serverUrl);
    }
  });

  console.log(`[dev-supervisor] waiting for server at ${serverUrl}/api/status ...`);
  const waitOnServer = spawnManaged("waitOnServer", "npx", ["wait-on", `http-get://127.0.0.1:${port}/api/status`]);
  waitOnServer.on("exit", (code) => {
    if (code === 0 && !shuttingDown) {
      serverReady = true;
      maybeStartElectron(serverUrl);
    }
  });
})().catch((err) => {
  console.error("[dev-supervisor] fatal error:", err);
  shutdown(1);
});
