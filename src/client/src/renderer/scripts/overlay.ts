/** Overlay rendering — Tahoe liquid glass redesign */
export {};

const overlayTitle = document.getElementById("overlay-title")!;
const overlayIcon = document.getElementById("overlay-icon")!;
const content = document.getElementById("overlay-content")!;

function parseActions(text: string): string[] {
  const matches = text.match(/<action>([\s\S]*?)<\/action>/g);
  if (matches) {
    return matches.map((m) => m.replace(/<\/?action>/g, "").trim());
  }
  const clean = text.replace(/<[^>]+>/g, "").trim();
  return clean ? [clean] : [];
}

function escapeHtml(s: string): string {
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}

function updateSize() {
  requestAnimationFrame(() => {
    const overlay = document.getElementById("overlay")!;
    const height = Math.max(80, Math.min(500, overlay.scrollHeight + 8));
    powernap.resizeOverlay(height);
  });
}

function setHeaderState(title: string, icon: string, stateClass: string) {
  overlayTitle.textContent = title;
  overlayTitle.className = stateClass;
  overlayIcon.textContent = icon;
  overlayIcon.className = "header-icon " + stateClass;
}

function showWaiting() {
  setHeaderState("Not Ready", "\u25CB", "");
  content.className = "";
  content.innerHTML = "Still labeling data\u2026<br>Try again in a moment.";
  updateSize();
}

function showFlushing() {
  setHeaderState("Syncing\u2026", "\u21BB", "flushing");
  content.className = "";
  content.innerHTML = "Labeling recent activity for fresh predictions\u2026";
  updateSize();
}

function showPrediction(actions: string[]) {
  setHeaderState("Predicted Actions", "\u2713", "predicted");
  content.className = "actions";
  content.innerHTML = actions
    .map(
      (a, i) =>
        `<div class="action-item"><span class="action-num">${i + 1}.</span><span class="action-text">${escapeHtml(a)}</span></div>`
    )
    .join("");
  updateSize();
}

// ── Event listeners ──────────────────────────────────────────

powernap.onOverlayWaiting(() => showWaiting());
powernap.onOverlayFlushing(() => showFlushing());

powernap.onOverlayPrediction((data: any) => {
  if (data.error) {
    showWaiting();
    return;
  }
  const actions = parseActions(data.actions || "");
  if (actions.length > 0) {
    showPrediction(actions);
  } else {
    showWaiting();
  }
});

showWaiting();
