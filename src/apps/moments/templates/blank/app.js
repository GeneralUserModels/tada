// ── Data ─────────────────────────────────────────────────
// Replace this object with your actual data.
const DATA = {
  title: "Moment Title",
  subtitle: "A brief description of what this moment shows",
};

// ── Render ───────────────────────────────────────────────
function render() {
  const app = document.getElementById("app");
  app.innerHTML = `
    <h1>${DATA.title}</h1>
    <p class="meta">${DATA.subtitle}</p>
    <div class="glass-card" style="margin-top: 16px;">
      <p>Build your moment interface here.</p>
    </div>
  `;
}

render();
