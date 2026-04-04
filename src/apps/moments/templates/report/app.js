// ── Data ─────────────────────────────────────────────────
// Replace with your actual data.
const DATA = {
  title: "Weekly Security Report",
  subtitle: "Generated April 3, 2026",
  status: { text: "Resolved", type: "success" }, // success | warning | danger | info
  sections: [
    {
      title: "Summary",
      content: "<p>A brief overview of the report findings and key takeaways.</p>",
      collapsed: false,
    },
    {
      title: "Details",
      content: "<ul><li>Finding one with relevant context.</li><li>Finding two with impact analysis.</li></ul>",
      collapsed: true,
    },
    {
      title: "Recommendations",
      content: "<p>Specific recommendations based on the analysis above.</p>",
      collapsed: true,
    },
  ],
  actions: [
    { title: "Review findings", description: "Check the detailed analysis for accuracy.", done: true },
    { title: "Update configuration", description: "Apply the recommended changes.", done: false },
    { title: "Monitor for 24h", description: "Watch metrics after applying changes.", done: false },
  ],
  timeline: [
    { date: "Apr 1", title: "Issue detected", description: "Automated monitoring flagged anomaly." },
    { date: "Apr 2", title: "Investigation", description: "Root cause identified and documented." },
    { date: "Apr 3", title: "Resolution", description: "Fix deployed and verified." },
  ],
};

// ── App ─────────────────────────────────────────────────
const h = React.createElement;
const { useState } = React;
const { PageHeader, GlassCard } = PN;

/** Collapsible section with toggle (template-specific) */
function CollapsibleSection({ title, content, initialCollapsed, delay }) {
  var [collapsed, setCollapsed] = useState(initialCollapsed);

  return h(GlassCard, { delay: delay },
    h("button", {
      className: "collapsible-toggle",
      onClick: function() { setCollapsed(!collapsed); }
    },
      h("span", { className: "section-title" }, title),
      h("span", { className: "chevron" }, collapsed ? "\u25B6" : "\u25BC")
    ),
    collapsed ? null : h("div", { style: { marginTop: "10px" } },
      h("div", { className: "section-content", dangerouslySetInnerHTML: { __html: content } })
    )
  );
}

/** Action item with checkbox (template-specific) */
function ActionItem({ title, description, done }) {
  return h("div", { className: "action-item" },
    h("div", { className: "action-check" + (done ? " done" : "") }, done ? "\u2713" : ""),
    h("div", null,
      h("div", { className: "action-title", style: done ? { textDecoration: "line-through", opacity: 0.6 } : {} }, title),
      description ? h("div", { className: "action-desc" }, description) : null
    )
  );
}

/** Timeline with dots and dates (template-specific) */
function Timeline({ items }) {
  if (!items || !items.length) return null;
  return h("div", null,
    h("h2", { className: "timeline-header" }, "Timeline"),
    h("div", { className: "timeline" },
      items.map(function(t, i) {
        return h("div", { key: i, className: "timeline-item" },
          h("div", { className: "timeline-dot" }),
          h("div", { className: "timeline-date" }, t.date),
          h("div", { className: "timeline-title" }, t.title),
          t.description ? h("div", { className: "timeline-desc" }, t.description) : null
        );
      })
    )
  );
}

function ReportApp() {
  var done = DATA.actions ? DATA.actions.filter(function(a) { return a.done; }).length : 0;

  return h("div", { className: "container" },
    h(PageHeader, { title: DATA.title, subtitle: DATA.subtitle, status: DATA.status }),

    // Sections
    DATA.sections.map(function(s, i) {
      return h(CollapsibleSection, {
        key: i,
        title: s.title,
        content: s.content,
        initialCollapsed: s.collapsed,
        delay: i * 0.04
      });
    }),

    // Actions
    DATA.actions && DATA.actions.length ? h("div", null,
      h("h2", { className: "actions-header" }, "Action Items (" + done + "/" + DATA.actions.length + ")"),
      DATA.actions.map(function(a, i) {
        return h(ActionItem, { key: i, title: a.title, description: a.description, done: a.done });
      })
    ) : null,

    // Timeline
    h(Timeline, { items: DATA.timeline })
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(h(ReportApp));
