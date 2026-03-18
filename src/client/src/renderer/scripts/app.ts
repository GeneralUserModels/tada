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

    // Load connector status when switching to connectors view
    if (panelId === "connectors-view") {
      loadConnectors();
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

btnSaveSettings.addEventListener("click", async () => {
  const data: Record<string, unknown> = {};
  for (const [elemId, key] of settingsFields) {
    const val = ($(elemId) as HTMLInputElement).value.trim();
    if (val) {
      data[key] = key === "fps" ? parseInt(val, 10) : val;
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

// ── Connectors ───────────────────────────────────────────

interface ConnectorInfo {
  enabled: boolean;
  available: boolean;
  configured: boolean;
}

const connectorMeta: Record<string, { label: string; desc: string; icon: string }> = {
  screen:           { label: "Screen Recording",  desc: "Captures your screen to observe workflow",       icon: "monitor" },
  calendar:         { label: "Google Calendar",    desc: "Read your upcoming events for context",          icon: "calendar" },
  gmail:            { label: "Gmail",              desc: "Read recent emails for context",                 icon: "mail" },
  outlook_calendar: { label: "Outlook Calendar",   desc: "Read your upcoming Outlook events for context",  icon: "calendar" },
  outlook_email:    { label: "Outlook Email",      desc: "Read recent Outlook emails for context",         icon: "mail" },
  notifications:    { label: "Notifications",      desc: "Read macOS notification history",                icon: "bell" },
  filesystem:       { label: "Filesystem",         desc: "Watch Desktop, Documents, Downloads",            icon: "folder" },
};

const connectorIcons: Record<string, string> = {
  monitor:  '<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><rect x="2" y="3" width="12" height="10" rx="2" stroke="currentColor" stroke-width="1.3"/><circle cx="8" cy="8" r="2" fill="currentColor"/></svg>',
  calendar: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><rect x="2" y="3" width="12" height="11" rx="1.5" stroke="currentColor" stroke-width="1.3"/><path d="M2 6.5h12" stroke="currentColor" stroke-width="1.3"/><path d="M5 1.5v3M11 1.5v3" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>',
  mail:     '<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><rect x="1.5" y="3.5" width="13" height="9" rx="1.5" stroke="currentColor" stroke-width="1.3"/><path d="M1.5 4.5L8 9l6.5-4.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  bell:     '<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M4 6a4 4 0 018 0v3l1.5 2H2.5L4 9V6z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/><path d="M6.5 13a1.5 1.5 0 003 0" stroke="currentColor" stroke-width="1.3"/></svg>',
  folder:   '<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M2 4.5V13a1 1 0 001 1h10a1 1 0 001-1V6a1 1 0 00-1-1H7.5L6 3H3a1 1 0 00-1 1.5z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>',
};

const dashConnectors = $("dashboard-connectors");

async function loadConnectors() {
  try {
    const status = (await powernap.getConnectorStatus()) as Record<string, ConnectorInfo>;
    dashConnectors.innerHTML = "";

    // Determine which Google services are currently connected (for scope management)
    const calendarOn = status.calendar?.enabled && status.calendar?.available;
    const gmailOn = status.gmail?.enabled && status.gmail?.available;

    for (const [name, info] of Object.entries(status)) {
      const meta = connectorMeta[name];
      if (!meta) continue;

      const row = document.createElement("div");
      row.style.cssText = "display:flex;align-items:center;gap:12px;padding:10px 12px;border-radius:8px;";

      const iconHtml = connectorIcons[meta.icon] || "";
      const connected = info.enabled && info.available;

      let actionHtml = "";
      if (!info.configured && name.startsWith("outlook_")) {
        // Outlook — use shared Microsoft auth
        actionHtml = `<button class="pill-btn pill-start" style="font-size:10px;padding:3px 10px;" data-connect-outlook="${name}">Connect</button>`;
      } else if (!info.configured) {
        // Never went through OAuth / setup — show Connect button
        actionHtml = `<button class="pill-btn pill-start" style="font-size:10px;padding:3px 10px;" data-connect-scope="${name}">Connect</button>`;
      } else {
        // Configured — show on/off toggle
        const checked = info.enabled ? "checked" : "";
        const bg = info.enabled ? '#84B179' : 'rgba(132,177,121,0.15)';
        const knobX = info.enabled ? 'translateX(16px)' : 'translateX(0)';
        actionHtml = `<label style="position:relative;display:inline-block;width:36px;height:20px;cursor:pointer;">
          <input type="checkbox" ${checked} data-connector="${name}" style="opacity:0;width:0;height:0;position:absolute;">
          <span style="position:absolute;inset:0;background:${bg};border-radius:20px;transition:background 0.2s;"></span>
          <span style="position:absolute;height:14px;width:14px;left:3px;bottom:3px;background:#fff;border-radius:50%;transition:transform 0.2s;box-shadow:0 1px 3px rgba(0,0,0,0.15);transform:${knobX};"></span>
        </label>`;
      }

      row.innerHTML = `
        <div style="width:28px;height:28px;border-radius:6px;display:flex;align-items:center;justify-content:center;background:rgba(199,234,187,0.3);color:#84B179;flex-shrink:0;">${iconHtml}</div>
        <div style="flex:1;min-width:0;">
          <div style="font-size:12.5px;font-weight:600;">${escapeHtml(meta.label)}</div>
          <div style="font-size:11px;color:#9BA896;">${escapeHtml(meta.desc)}</div>
        </div>
        <div style="display:flex;align-items:center;gap:8px;flex-shrink:0;">${actionHtml}</div>
      `;
      dashConnectors.appendChild(row);
    }

    // Bind Google connect buttons (scope-aware)
    dashConnectors.querySelectorAll<HTMLElement>("[data-connect-scope]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const svc = (btn as HTMLElement).dataset.connectScope!;
        // Preserve existing Google scopes when adding a new one
        const otherOn = svc === "calendar" ? gmailOn : calendarOn;
        const scope = otherOn ? "calendar,gmail" : svc;

        btn.textContent = "Connecting...";
        (btn as HTMLButtonElement).disabled = true;
        const ok = await powernap.connectorConnectGoogle(scope);
        if (ok) {
          // Mark this service as enabled in config
          await powernap.updateConnector(svc, true);
        }
        loadConnectors();
      });
    });

    // Bind Outlook connect buttons
    dashConnectors.querySelectorAll<HTMLElement>("[data-connect-outlook]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        btn.textContent = "Connecting...";
        (btn as HTMLButtonElement).disabled = true;
        const ok = await powernap.connectorConnectOutlook();
        if (ok) {
          await powernap.updateConnector("outlook_calendar", true);
          await powernap.updateConnector("outlook_email", true);
        }
        loadConnectors();
      });
    });

    dashConnectors.querySelectorAll<HTMLInputElement>("[data-connector]").forEach((input) => {
      input.addEventListener("change", async () => {
        // Immediately update toggle visuals
        const label = input.closest("label");
        if (label) {
          const track = label.children[1] as HTMLElement;
          const knob = label.children[2] as HTMLElement;
          if (track) track.style.background = input.checked ? '#84B179' : 'rgba(132,177,121,0.15)';
          if (knob) knob.style.transform = input.checked ? 'translateX(16px)' : 'translateX(0)';
        }
        await powernap.updateConnector(input.dataset.connector!, input.checked);
      });
    });
  } catch {
    dashConnectors.innerHTML = '<div style="color:#9BA896;font-size:12px;padding:12px;">Unable to load connector status.</div>';
  }
}

// ── Auto-update modal ────────────────────────────────────────

const updateModalOverlay = $("update-modal-overlay");
const updateModalMessage = $("update-modal-message");
const btnUpdateNow = $("btn-update-now") as HTMLButtonElement;
const btnUpdateOnQuit = $("btn-update-on-quit") as HTMLButtonElement;
const btnUpdateLater = $("btn-update-later") as HTMLButtonElement;

powernap.onUpdateDownloaded((data: any) => {
  updateModalMessage.textContent = `Version ${data.version} has been downloaded and is ready to install.`;
  updateModalOverlay.style.display = "flex";
});

btnUpdateNow.addEventListener("click", () => {
  updateModalOverlay.style.display = "none";
  powernap.installNow();
});

btnUpdateOnQuit.addEventListener("click", () => {
  powernap.installOnNextLaunch();
  updateModalOverlay.style.display = "none";
});

btnUpdateLater.addEventListener("click", () => {
  powernap.dismissUpdate();
  updateModalOverlay.style.display = "none";
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

      // Populate settings fields from server
      try {
        const settings = (await powernap.getSettings()) as Record<string, unknown>;
        for (const [elemId, key] of settingsFields) {
          const val = settings[key];
          if (val !== undefined && val !== null && val !== "") {
            ($(elemId) as HTMLInputElement).value = String(val);
          }
        }
      } catch { /* settings fetch failed */ }
    }
  } catch {
    // Server not running yet
  }
});
