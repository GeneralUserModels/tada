/** Dashboard logic — macOS Tahoe redesign */
export {};

// ── DOM refs ─────────────────────────────────────────────────

const $ = (id: string) => document.getElementById(id)!;

const btnRecordStart = $("btn-record-start") as HTMLButtonElement;
const btnRecordStop = $("btn-record-stop") as HTMLButtonElement;
const btnTrainStart = $("btn-train-start") as HTMLButtonElement;
const btnTrainStop = $("btn-train-stop") as HTMLButtonElement;
const btnGenerate = $("btn-generate") as HTMLButtonElement;
const btnSaveSettings = $("btn-save-settings") as HTMLButtonElement;

const recordingIndicator = $("recording-indicator");
const trainingIndicator = $("training-indicator");
const inferenceIndicator = $("inference-indicator");

const tileRecording = $("tile-recording");
const tileTraining = $("tile-training");
const tileInference = $("tile-inference");

const predictionContent = $("prediction-content");
const predictionTimestamp = $("prediction-timestamp");

const rewardCanvas = $("reward-chart") as HTMLCanvasElement;
const elboScore = $("elbo-score");

// ── Reward history ──────────────────────────────────────────

const rewardHistory: {step: number; accuracy: number; formatting: number; combined: number}[] = [];

function drawChart() {
  const ctx = rewardCanvas.getContext("2d");
  if (!ctx) return;

  const dpr = window.devicePixelRatio || 1;
  const rect = rewardCanvas.getBoundingClientRect();
  rewardCanvas.width = rect.width * dpr;
  rewardCanvas.height = rect.height * dpr;
  ctx.scale(dpr, dpr);

  const W = rect.width;
  const H = rect.height;
  ctx.clearRect(0, 0, W, H);

  if (rewardHistory.length === 0) return;

  // Layout
  const padLeft = 36;
  const padRight = 12;
  const padTop = 8;
  const padBottom = 22;
  const plotW = W - padLeft - padRight;
  const plotH = H - padTop - padBottom;

  // Y-axis: 0 to max (at least 1)
  let yMax = 0;
  for (const pt of rewardHistory) {
    yMax = Math.max(yMax, pt.accuracy, pt.formatting, pt.combined);
  }
  yMax = Math.max(1, Math.ceil(yMax * 10) / 10);

  // Grid lines
  const gridSteps = 4;
  ctx.strokeStyle = "rgba(132,177,121,0.12)";
  ctx.lineWidth = 1;
  ctx.font = "10px -apple-system, BlinkMacSystemFont, sans-serif";
  ctx.fillStyle = "#9BA896";
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";

  for (let i = 0; i <= gridSteps; i++) {
    const y = padTop + plotH - (i / gridSteps) * plotH;
    ctx.beginPath();
    ctx.moveTo(padLeft, y);
    ctx.lineTo(padLeft + plotW, y);
    ctx.stroke();
    const label = ((i / gridSteps) * yMax).toFixed(1);
    ctx.fillText(label, padLeft - 6, y);
  }

  // X helper
  const xOf = (idx: number) => padLeft + (idx / Math.max(1, rewardHistory.length - 1)) * plotW;
  const yOf = (val: number) => padTop + plotH - (val / yMax) * plotH;

  // Draw lines
  const series: {key: keyof typeof rewardHistory[0]; color: string}[] = [
    {key: "accuracy", color: "#5DA34E"},
    {key: "formatting", color: "#C9944B"},
    {key: "combined", color: "#2C3A28"},
  ];

  for (const s of series) {
    ctx.beginPath();
    ctx.strokeStyle = s.color;
    ctx.lineWidth = 1.8;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";

    for (let i = 0; i < rewardHistory.length; i++) {
      const x = xOf(i);
      const y = yOf(rewardHistory[i][s.key] as number);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();
  }

  // X-axis step labels
  ctx.fillStyle = "#9BA896";
  ctx.textAlign = "center";
  ctx.textBaseline = "top";

  const maxLabels = Math.min(6, rewardHistory.length);
  if (rewardHistory.length <= maxLabels) {
    for (let i = 0; i < rewardHistory.length; i++) {
      ctx.fillText(String(rewardHistory[i].step), xOf(i), padTop + plotH + 6);
    }
  } else {
    for (let i = 0; i < maxLabels; i++) {
      const idx = Math.round((i / (maxLabels - 1)) * (rewardHistory.length - 1));
      ctx.fillText(String(rewardHistory[idx].step), xOf(idx), padTop + plotH + 6);
    }
  }
}

const historyList = $("history-list");

const statLabels = $("stat-labels");
const statQueue = $("stat-queue");
const statStep = $("stat-step");
const statBuffer = $("stat-buffer");

// ── Sidebar navigation ──────────────────────────────────────

document.querySelectorAll<HTMLButtonElement>(".nav-item").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".nav-item").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");

    const panelId = btn.dataset.panel!;
    document.querySelectorAll<HTMLElement>(".view").forEach((v) => {
      v.classList.toggle("active", v.id === panelId);
    });

    // Redraw chart when switching back to dashboard (canvas has zero size while hidden)
    if (panelId === "view-dashboard" && rewardHistory.length > 0) {
      requestAnimationFrame(() => drawChart());
    }
  });
});

// ── Control buttons ──────────────────────────────────────────

type TileState = "idle" | "starting" | "running" | "stopping";

const stateLabels: Record<TileState, string> = {
  idle: "Idle",
  starting: "Starting\u2026",
  running: "Running",
  stopping: "Stopping\u2026",
};

function setControlState(
  startBtn: HTMLButtonElement,
  stopBtn: HTMLButtonElement,
  indicator: HTMLElement,
  tile: HTMLElement,
  state: TileState
) {
  startBtn.disabled = state !== "idle";
  stopBtn.disabled = state !== "running";
  indicator.textContent = stateLabels[state];
  indicator.classList.toggle("active", state === "running");
  indicator.classList.toggle("transitioning", state === "starting" || state === "stopping");
  tile.classList.toggle("running", state === "running");
}

btnRecordStart.addEventListener("click", async () => {
  setControlState(btnRecordStart, btnRecordStop, recordingIndicator, tileRecording, "starting");
  await powernap.startRecording();
  setControlState(btnRecordStart, btnRecordStop, recordingIndicator, tileRecording, "running");
});
btnRecordStop.addEventListener("click", async () => {
  setControlState(btnRecordStart, btnRecordStop, recordingIndicator, tileRecording, "stopping");
  await powernap.stopRecording();
  setControlState(btnRecordStart, btnRecordStop, recordingIndicator, tileRecording, "idle");
});
btnTrainStart.addEventListener("click", async () => {
  setControlState(btnTrainStart, btnTrainStop, trainingIndicator, tileTraining, "starting");
  await powernap.startTraining();
  setControlState(btnTrainStart, btnTrainStop, trainingIndicator, tileTraining, "running");
});
btnTrainStop.addEventListener("click", async () => {
  setControlState(btnTrainStart, btnTrainStop, trainingIndicator, tileTraining, "stopping");
  await powernap.stopTraining();
  setControlState(btnTrainStart, btnTrainStop, trainingIndicator, tileTraining, "idle");
});
function setGenerateState(generating: boolean) {
  btnGenerate.disabled = generating;
  btnGenerate.textContent = generating ? "Generating Predictions\u2026" : "Generate Predictions";
  inferenceIndicator.textContent = generating ? "Generating\u2026" : "Idle";
  inferenceIndicator.classList.toggle("transitioning", generating);
  inferenceIndicator.classList.toggle("active", false);
  tileInference.classList.toggle("running", generating);
}

btnGenerate.addEventListener("click", async () => {
  setGenerateState(true);
  await powernap.startInference();
  await powernap.requestPrediction();
});

// ── Settings ─────────────────────────────────────────────────

const settingsFields: [string, string][] = [
  ["set-gemini-key", "gemini_api_key"],
  ["set-tinker-key", "tinker_api_key"],
  ["set-hf-token", "hf_token"],
  ["set-wandb-key", "wandb_api_key"],
  ["set-model", "model"],
  ["set-reward-llm", "reward_llm"],
  ["set-fps", "fps"],
];

// Restore saved settings on load
for (const [elemId, key] of settingsFields) {
  const saved = localStorage.getItem(`powernap_${key}`);
  if (saved) {
    ($(elemId) as HTMLInputElement).value = saved;
  }
}

btnSaveSettings.addEventListener("click", async () => {
  const data: Record<string, unknown> = {};
  for (const [elemId, key] of settingsFields) {
    const val = ($(elemId) as HTMLInputElement).value.trim();
    if (val) {
      data[key] = key === "fps" ? parseInt(val, 10) : val;
      localStorage.setItem(`powernap_${key}`, val);
    }
  }
  if (Object.keys(data).length > 0) {
    await powernap.updateSettings(data);
  }
});

// ── Helpers ──────────────────────────────────────────────────

function parseActions(text: string): string[] {
  const matches = text.match(/<action>([\s\S]*?)<\/action>/g);
  if (matches) {
    return matches.map((m) => m.replace(/<\/?action>/g, "").trim());
  }
  return [text.replace(/<[^>]+>/g, "").trim()];
}

function escapeHtml(s: string): string {
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}

function addHistoryItem(type: string, text: string, timestamp: string) {
  const item = document.createElement("div");
  item.className = "history-item";

  const badgeClass: Record<string, string> = {
    prediction: "badge-prediction",
    label: "badge-label",
    training: "badge-training",
  };

  const preview = (text || "").substring(0, 140);
  item.innerHTML = `
    <span class="history-badge ${badgeClass[type] || ''}">${type}</span>
    <div>
      <div class="history-text">${escapeHtml(preview)}</div>
      ${timestamp ? `<div class="history-meta">${escapeHtml(timestamp)}</div>` : ""}
    </div>
  `;

  historyList.prepend(item);

  while (historyList.children.length > 100) {
    historyList.removeChild(historyList.lastChild!);
  }
}

// ── Event handlers ───────────────────────────────────────────

powernap.onPrediction((data: any) => {
  setGenerateState(false);

  if (data.error) {
    predictionContent.innerHTML = `<span class="empty-state">${escapeHtml(data.error)}</span>`;
    return;
  }
  const actions = parseActions(data.actions || "");
  predictionContent.innerHTML = actions
    .map(
      (a, i) =>
        `<div class="action-line"><span class="action-num">${i + 1}.</span> ${escapeHtml(a)}</div>`
    )
    .join("");
  predictionTimestamp.textContent = data.timestamp || "";

  addHistoryItem("prediction", data.actions, data.timestamp);
});

powernap.onPredictionRequested(() => {
  setGenerateState(true);
});

powernap.onScore((data: any) => {
  const acc = data.accuracy ?? 0;
  const fmt = data.formatting ?? 0;
  const combined = data.reward ?? 0;

  rewardHistory.push({
    step: rewardHistory.length,
    accuracy: acc,
    formatting: fmt,
    combined,
  });
  drawChart();
});

powernap.onElboScore((data: any) => {
  const mean = (data.logprob_reward_mean ?? 0).toFixed(4);
  const std = (data.logprob_reward_std ?? 0).toFixed(4);
  elboScore.textContent = `ELBO ${mean} \u00B1 ${std}`;
});

powernap.onTrainingStep((data: any) => {
  statStep.textContent = String(data.step ?? 0);

  rewardHistory.push({
    step: data.step ?? 0,
    accuracy: data.accuracy_mean ?? 0,
    formatting: data.formatting_mean ?? 0,
    combined: data.reward_mean ?? 0,
  });
  drawChart();

  addHistoryItem(
    "training",
    `Step ${data.step}: loss=${(data.loss ?? 0).toFixed(4)}, reward=${(data.reward_mean ?? 0).toFixed(4)}`,
    ""
  );
});

powernap.onLabel((data: any) => {
  statLabels.textContent = String(data.count ?? 0);
  addHistoryItem("label", data.text || "", "");
});

powernap.onStatusUpdate((data: any) => {
  setControlState(btnRecordStart, btnRecordStop, recordingIndicator, tileRecording, data.recording_active ? "running" : "idle");
  setControlState(btnTrainStart, btnTrainStop, trainingIndicator, tileTraining, data.training_active ? "running" : "idle");
  statQueue.textContent = String(data.untrained_batches ?? 0);
  statLabels.textContent = String(data.labels_processed ?? 0);
  statBuffer.textContent = String(data.inference_buffer_size ?? 0);
});

// ── Initial fetch ────────────────────────────────────────────

powernap.onServerReady(async () => {
  try {
    const status = (await powernap.getStatus()) as any;
    if (status) {
      setControlState(btnRecordStart, btnRecordStop, recordingIndicator, tileRecording, status.recording_active ? "running" : "idle");
      setControlState(btnTrainStart, btnTrainStop, trainingIndicator, tileTraining, status.training_active ? "running" : "idle");
      statLabels.textContent = String(status.labels_processed ?? 0);
      statQueue.textContent = String(status.untrained_batches ?? 0);
      statStep.textContent = String(status.step_count ?? 0);
      statBuffer.textContent = String(status.inference_buffer_size ?? 0);
      $("connection-status").classList.replace("disconnected", "connected");

      // Seed reward chart from persisted history
      try {
        const history = (await powernap.getTrainingHistory()) as any[];
        if (Array.isArray(history)) {
          for (const pt of history) {
            rewardHistory.push({
              step: pt.step ?? 0,
              accuracy: pt.accuracy_mean ?? 0,
              formatting: pt.formatting_mean ?? 0,
              combined: pt.reward_mean ?? 0,
            });
          }
          if (rewardHistory.length > 0) {
            drawChart();
            statStep.textContent = String(rewardHistory[rewardHistory.length - 1].step);
          }
        }
      } catch { /* metrics.jsonl may not exist yet */ }

      // Auto-send saved settings to server on connect
      const saved: Record<string, unknown> = {};
      for (const [elemId, key] of settingsFields) {
        const val = localStorage.getItem(`powernap_${key}`);
        if (val) {
          saved[key] = key === "fps" ? parseInt(val, 10) : val;
        }
      }
      if (Object.keys(saved).length > 0) {
        await powernap.updateSettings(saved);
      }
    }
  } catch {
    // Server not running yet
  }
});
