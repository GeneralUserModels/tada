// ── Data ─────────────────────────────────────────────────
// Replace with your actual data. Each tab contains a list of items.
const DATA = {
  title: "Daily Research Digest",
  subtitle: "Updated April 3, 2026",
  tags: ["Machine Learning", "Reasoning", "Agents"],
  stats: [
    { value: "12", label: "Papers" },
    { value: "8", label: "Threads" },
    { value: "3", label: "Posts" },
  ],
  tabs: [
    {
      id: "papers", label: "Papers",
      items: [
        {
          title: "Sample Paper Title",
          url: "https://arxiv.org/abs/2403.00000",
          meta: "Chen et al. — arXiv, Mar 2026",
          summary: "A brief summary of what this paper covers and why it is relevant.",
          score: 9,
          tags: ["reasoning", "agents"],
        },
        {
          title: "Another Paper Title",
          url: "https://arxiv.org/abs/2403.00001",
          meta: "Smith et al. — NeurIPS 2026",
          summary: "Another summary describing the contribution.",
          score: 7,
          tags: ["training"],
        },
      ],
    },
    {
      id: "threads", label: "Threads",
      items: [
        {
          title: "@researcher — Interesting findings on...",
          url: "https://x.com/researcher/status/123",
          meta: "2h ago — 1.2k likes",
          summary: "Key takeaway from this thread about recent developments.",
          score: 8,
          tags: ["discussion"],
        },
      ],
    },
  ],
};

// ── App ─────────────────────────────────────────────────
const h = React.createElement;
const { useState } = React;
const { PageHeader, StatRow, TabBar, GlassCard, EmptyState } = PN;

/** Score circle indicator (template-specific component) */
function ScoreCircle({ score }) {
  if (score == null) return null;
  return h("div", { className: "score" + (score >= 8 ? " high" : "") }, score);
}

/** Feed item card with score and tags */
function FeedCard({ item, delay }) {
  return h(GlassCard, { delay: delay },
    h("div", { className: "card-header" },
      h("div", null,
        h("div", { className: "card-title" },
          item.url ? h("a", { href: item.url, target: "_blank" }, item.title) : item.title
        ),
        h("div", { className: "card-meta" }, item.meta || "")
      ),
      h(ScoreCircle, { score: item.score })
    ),
    item.summary ? h("div", { className: "card-summary" }, item.summary) : null,
    item.tags && item.tags.length ? h("div", { className: "card-tags" },
      item.tags.map(function(t, i) {
        return h("span", { key: i, className: "card-tag" }, t);
      })
    ) : null
  );
}

function FeedApp() {
  var [activeTab, setActiveTab] = useState(DATA.tabs[0] ? DATA.tabs[0].id : null);

  var tabs = DATA.tabs.map(function(t) {
    return { id: t.id, label: t.label, count: t.items.length };
  });

  var currentTab = DATA.tabs.find(function(t) { return t.id === activeTab; });
  var items = currentTab ? currentTab.items : [];

  return h("div", { className: "container" },
    h(PageHeader, { title: DATA.title, subtitle: DATA.subtitle, badges: DATA.tags }),
    h(StatRow, { stats: DATA.stats }),
    h(TabBar, { tabs: tabs, active: activeTab, onChange: setActiveTab }),
    items.length === 0
      ? h(EmptyState, { message: "No items yet." })
      : items.map(function(item, i) {
          return h(FeedCard, { key: i, item: item, delay: i * 0.04 });
        })
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(h(FeedApp));
