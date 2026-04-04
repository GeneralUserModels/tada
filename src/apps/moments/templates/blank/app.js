// ── Data ─────────────────────────────────────────────────
// Replace this object with your actual data.
const DATA = {
  title: "Moment Title",
  subtitle: "A brief description of what this moment shows",
};

// ── App ─────────────────────────────────────────────────
const h = React.createElement;
const { PageHeader, GlassCard } = PN;

function BlankApp() {
  return h("div", { className: "container" },
    h(PageHeader, { title: DATA.title, subtitle: DATA.subtitle }),
    h(GlassCard, { style: { marginTop: "16px" } },
      h("p", null, "Build your moment interface here.")
    )
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(h(BlankApp));
