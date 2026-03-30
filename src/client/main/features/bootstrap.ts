/** First-launch bootstrap: installs uv, Python 3.12, and all pip dependencies. */

import { spawn } from "child_process";
import * as fs from "fs";
import * as crypto from "crypto";
import * as path from "path";
import * as https from "https";
import { getDataDir, getUvPath, getRgPath, getPythonPath, getPythonSrcDir } from "./paths";

type ProgressCallback = (msg: string, pct: number) => void;
type LogCallback = (line: string) => void;

const UV_VERSION = "0.6.6";
const RG_VERSION = "14.1.1";

function getRequirementsPath(): string {
  return path.join(getPythonSrcDir(), "requirements.txt");
}

function getSentinelPath(): string {
  return path.join(getDataDir(), ".bootstrap-version");
}

function hashFile(filePath: string): string {
  const content = fs.readFileSync(filePath, "utf-8");
  return crypto.createHash("sha256").update(content).digest("hex").slice(0, 16);
}

export function isReady(): boolean {
  const pythonPath = getPythonPath();
  const sentinelPath = getSentinelPath();

  if (!fs.existsSync(pythonPath) || !fs.existsSync(sentinelPath)) {
    return false;
  }

  const reqPath = getRequirementsPath();
  if (!fs.existsSync(reqPath)) {
    return false;
  }

  const currentHash = hashFile(reqPath);
  const savedHash = fs.readFileSync(sentinelPath, "utf-8").trim();
  return currentHash === savedHash;
}

function runCommand(
  cmd: string,
  args: string[],
  onLog?: LogCallback,
  env?: Record<string, string>,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const proc = spawn(cmd, args, {
      stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env, ...env },
    });

    let stderr = "";
    proc.stderr?.on("data", (chunk: Buffer) => {
      const text = chunk.toString();
      stderr += text;
      for (const line of text.split("\n").filter(Boolean)) {
        onLog?.(line.trim());
      }
    });
    proc.stdout?.on("data", (chunk: Buffer) => {
      const text = chunk.toString();
      process.stdout.write(`[bootstrap] ${text}`);
      for (const line of text.split("\n").filter(Boolean)) {
        onLog?.(line.trim());
      }
    });

    proc.on("exit", (code) => {
      if (code === 0) {
        resolve();
      } else {
        reject(new Error(`Command "${cmd} ${args.join(" ")}" exited with code ${code}\n${stderr}`));
      }
    });

    proc.on("error", reject);
  });
}

function downloadFile(url: string, dest: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const file = fs.createWriteStream(dest);
    const request = (reqUrl: string) => {
      https.get(reqUrl, (res) => {
        if (res.statusCode === 301 || res.statusCode === 302) {
          request(res.headers.location!);
          return;
        }
        if (res.statusCode !== 200) {
          reject(new Error(`Download failed: HTTP ${res.statusCode}`));
          return;
        }
        res.pipe(file);
        file.on("finish", () => {
          file.close();
          resolve();
        });
      }).on("error", (err) => {
        fs.unlink(dest, () => {});
        reject(err);
      });
    };
    request(url);
  });
}

export async function run(onProgress: ProgressCallback, onLog?: LogCallback): Promise<void> {
  const dataDir = getDataDir();
  fs.mkdirSync(dataDir, { recursive: true });

  const uvPath = getUvPath();
  const venvDir = path.join(dataDir, "venv");
  const pythonPath = getPythonPath();
  const reqPath = getRequirementsPath();

  // Step 1: Download uv
  if (!fs.existsSync(uvPath)) {
    onProgress("Downloading uv package manager...", 5);
    const arch = process.arch === "arm64" ? "aarch64" : "x86_64";
    const uvUrl = `https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/uv-${arch}-apple-darwin.tar.gz`;
    const tarPath = path.join(dataDir, "uv.tar.gz");

    await downloadFile(uvUrl, tarPath);
    onProgress("Extracting uv...", 10);
    await runCommand("tar", ["xzf", tarPath, "-C", dataDir, "--strip-components=1"], onLog);
    fs.unlinkSync(tarPath);

    // Ensure uv is executable
    fs.chmodSync(uvPath, 0o755);
  }

  // Step 1b: Download ripgrep
  const rgPath = getRgPath();
  if (!fs.existsSync(rgPath)) {
    onProgress("Downloading ripgrep...", 12);
    const arch = process.arch === "arm64" ? "aarch64" : "x86_64";
    const rgUrl = `https://github.com/BurntSushi/ripgrep/releases/download/${RG_VERSION}/ripgrep-${RG_VERSION}-${arch}-apple-darwin.tar.gz`;
    const rgTarPath = path.join(dataDir, "rg.tar.gz");

    await downloadFile(rgUrl, rgTarPath);
    onProgress("Extracting ripgrep...", 13);
    await runCommand("tar", ["xzf", rgTarPath, "-C", dataDir, "--strip-components=1"], onLog);
    fs.unlinkSync(rgTarPath);

    // The tarball extracts a "rg" binary
    fs.chmodSync(rgPath, 0o755);
  }

  // Step 2: Install Python 3.12
  onProgress("Installing Python 3.12...", 15);
  await runCommand(uvPath, ["python", "install", "3.12"], onLog);

  // Step 3: Create venv
  onProgress("Creating virtual environment...", 25);
  await runCommand(uvPath, ["venv", venvDir, "--python", "3.12"], onLog);

  // Step 4: Install requirements
  onProgress("Installing Python dependencies (this may take a few minutes)...", 40);
  await runCommand(uvPath, [
    "pip", "install",
    "-r", reqPath,
    "--python", pythonPath,
  ], onLog);

  // Step 5: Write sentinel
  onProgress("Finalizing setup...", 95);
  const hash = hashFile(reqPath);
  fs.writeFileSync(getSentinelPath(), hash, "utf-8");

  onProgress("Setup complete!", 100);
}
