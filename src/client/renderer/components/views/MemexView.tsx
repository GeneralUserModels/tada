import React, { useEffect, useState, useCallback, useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import { useAppContext } from "../../context/AppContext";
import { useMemory, WikiPage } from "../../hooks/useMemory";
import { FeatureActivityBanner } from "../FeatureActivityBanner";
import {
  stripFrontmatter,
  parseFrontmatter,
  processWikiLinks,
  processInlineConfidence,
  confidenceColor,
  confidenceLabel,
} from "./memexHelpers";

/** Format a relative time string. */
function timeAgo(dateStr: string): string {
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  if (isNaN(then)) return dateStr;
  const diff = now - then;
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  if (hours < 48) return "yesterday";
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(dateStr).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

/** Group pages by category. */
function groupByCategory(pages: WikiPage[]): Map<string, WikiPage[]> {
  const groups = new Map<string, WikiPage[]>();
  for (const page of pages) {
    const cat = page.category || "general";
    const list = groups.get(cat) || [];
    list.push(page);
    groups.set(cat, list);
  }
  return groups;
}

export function MemexView() {
  const { state } = useAppContext();
  const memoryActivity = state.agentActivities["memory"];
  const { pages, status, loading, load, getPage, savePage, deletePage } = useMemory();

  // Navigation state
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [pageContent, setPageContent] = useState<string>("");
  const [pageLoading, setPageLoading] = useState(false);

  // Edit state
  const [editing, setEditing] = useState(false);
  const [editContent, setEditContent] = useState("");
  const [saving, setSaving] = useState(false);

  // Delete state
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  // Search state
  const [search, setSearch] = useState("");

  useEffect(() => {
    if (state.connected) load();
  }, [state.connected, load]);

  const openPage = useCallback(async (path: string) => {
    setSelectedPath(path);
    setEditing(false);
    setPageLoading(true);
    const content = await getPage(path);
    setPageContent(content);
    setPageLoading(false);
  }, [getPage]);

  const handleBack = useCallback(() => {
    setSelectedPath(null);
    setPageContent("");
    setEditing(false);
    setConfirmingDelete(false);
  }, []);

  const handleEdit = useCallback(() => {
    setEditContent(pageContent);
    setEditing(true);
  }, [pageContent]);

  const handleCancel = useCallback(() => {
    setEditing(false);
  }, []);

  const handleSave = useCallback(async () => {
    if (!selectedPath) return;
    setSaving(true);
    await savePage(selectedPath, editContent);
    setPageContent(editContent);
    setEditing(false);
    setSaving(false);
    load();
  }, [selectedPath, editContent, savePage, load]);

  const handleDelete = useCallback(async () => {
    if (!selectedPath) return;
    setDeleting(true);
    await deletePage(selectedPath);
    setDeleting(false);
    setConfirmingDelete(false);
    setSelectedPath(null);
    setPageContent("");
    load();
  }, [selectedPath, deletePage, load]);

  // Handle wiki-link clicks
  const handleLinkClick = useCallback((href: string) => {
    if (!href.startsWith("wiki:")) return;
    const slug = href.slice(5);

    const normalize = (s: string) =>
      s.replace(/\.md$/, "").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[^a-z0-9\/]/g, "-").replace(/-+/g, "-").replace(/(^-|-$)/g, "");

    const normalizedSlug = normalize(slug);

    const target = pages.find((p) => {
      const n = normalize(p.path);
      return n === normalizedSlug || n.endsWith("/" + normalizedSlug);
    });
    if (target) openPage(target.path);
  }, [pages, openPage]);

  // Filtered pages
  const filteredPages = useMemo(() => {
    if (!search.trim()) return pages;
    const q = search.toLowerCase();
    return pages.filter(
      (p) => p.title.toLowerCase().includes(q) || (p.category || "").toLowerCase().includes(q)
    );
  }, [pages, search]);

  const grouped = useMemo(() => groupByCategory(filteredPages), [filteredPages]);

  const selectedPage = pages.find((p) => p.path === selectedPath);
  const fm = pageContent ? parseFrontmatter(pageContent) : {};

  // ── Page view (detail + edit) ──────────────────────────────

  if (selectedPath) {
    return (
      <div id="memex-view" className="view active">
        <div className="memex-detail-header glass-card">
          <button className="memex-back-btn" onClick={handleBack}>
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M9 2L4 7l5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            Back
          </button>
          <span className="memex-detail-title">{selectedPage?.title || fm.title || selectedPath}</span>
          {selectedPage?.confidence != null && (
            <span
              className="memex-confidence"
              style={{ background: `${confidenceColor(selectedPage.confidence)}18`, color: confidenceColor(selectedPage.confidence) }}
            >
              {(selectedPage.confidence * 100).toFixed(0)}% {confidenceLabel(selectedPage.confidence)}
            </span>
          )}
          <div className="memex-detail-actions">
            {editing ? (
              <>
                <button className="memex-action-btn memex-save-btn" onClick={handleSave} disabled={saving}>
                  {saving ? "Saving..." : "Save"}
                </button>
                <button className="memex-action-btn memex-cancel-btn" onClick={handleCancel}>
                  Cancel
                </button>
              </>
            ) : (
              <>
                <button className="memex-action-btn memex-edit-btn" onClick={handleEdit}>
                  <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
                    <path d="M10.5 1.5l2 2-8 8H2.5v-2l8-8z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round"/>
                  </svg>
                  Edit
                </button>
                <button className="memex-action-btn memex-delete-btn" onClick={() => setConfirmingDelete(true)}>
                  <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
                    <path d="M3 4h8l-.75 8.5a1 1 0 01-1 .9H4.75a1 1 0 01-1-.9L3 4z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round"/>
                    <path d="M5.5 6.5v4M8.5 6.5v4" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
                    <path d="M2 4h10M5.5 4V2.5a.5.5 0 01.5-.5h2a.5.5 0 01.5.5V4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                  Delete
                </button>
              </>
            )}
          </div>
        </div>

        {confirmingDelete && (
          <div className="memex-confirm-overlay">
            <div className="memex-confirm-dialog glass-card">
              <p>Delete <strong>{selectedPage?.title || selectedPath}</strong>?</p>
              <span className="memex-confirm-hint">This will permanently remove the page.</span>
              <div className="memex-confirm-actions">
                <button className="memex-action-btn memex-cancel-btn" onClick={() => setConfirmingDelete(false)}>
                  Cancel
                </button>
                <button className="memex-action-btn memex-confirm-delete-btn" onClick={handleDelete} disabled={deleting}>
                  {deleting ? "Deleting..." : "Delete"}
                </button>
              </div>
            </div>
          </div>
        )}

        {pageLoading ? (
          <div className="memex-empty-state">
            <div className="memex-spinner" />
          </div>
        ) : editing ? (
          <div className="memex-editor-wrap glass-card">
            <textarea
              className="memex-editor"
              value={editContent}
              onChange={(e) => setEditContent(e.target.value)}
              spellCheck={false}
            />
          </div>
        ) : (
          <div className="memex-content-wrap glass-card">
            <div className="memex-content">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                rehypePlugins={[rehypeRaw]}
                urlTransform={(url) => url}
                components={{
                  a: ({ href, children }) => {
                    if (href?.startsWith("wiki:")) {
                      return (
                        <a
                          className="memex-wiki-link"
                          href="#"
                          onClick={(e) => { e.preventDefault(); handleLinkClick(href); }}
                        >
                          {children}
                        </a>
                      );
                    }
                    return <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>;
                  },
                }}
              >
                {processInlineConfidence(processWikiLinks(stripFrontmatter(pageContent)))}
              </ReactMarkdown>
            </div>
            {(selectedPage?.last_updated || fm.last_updated) && (
              <div className="memex-meta">
                Last updated {selectedPage?.last_updated || fm.last_updated}
              </div>
            )}
          </div>
        )}
      </div>
    );
  }

  // ── List view ──────────────────────────────────────────────

  return (
    <div id="memex-view" className="view active">
      {memoryActivity && (
        <FeatureActivityBanner activity={memoryActivity} label="Memory" />
      )}
      <div className="memex-list-header">
        <div className="memex-search-wrap">
          <svg className="memex-search-icon" width="14" height="14" viewBox="0 0 14 14" fill="none">
            <circle cx="6" cy="6" r="4.5" stroke="currentColor" strokeWidth="1.3"/>
            <path d="M9.5 9.5L13 13" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
          </svg>
          <input
            className="memex-search"
            type="text"
            placeholder="Search pages..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        {status && (
          <div className="memex-status">
            <span>{status.page_count} page{status.page_count !== 1 ? "s" : ""}</span>
            {status.last_ingest && (
              <span className="memex-status-sep">Updated {timeAgo(status.last_ingest)}</span>
            )}
          </div>
        )}
      </div>

      {loading ? (
        <div className="memex-empty-state">
          <div className="memex-spinner" />
          <span>Loading wiki...</span>
        </div>
      ) : pages.length === 0 ? (
        <div className="memex-empty-state">
          <svg className="memex-empty-icon" width="32" height="32" viewBox="0 0 32 32" fill="none">
            <path d="M16 4C10.5 4 6 8.5 6 14c0 3 1.3 5.7 3.4 7.6.6.5 1 1.4 1 2.3V25c0 1.7 1.3 3 3 3h5.2c1.7 0 3-1.3 3-3v-1.1c0-.9.4-1.8 1-2.3C24.7 19.7 26 17 26 14c0-5.5-4.5-10-10-10z"
              stroke="var(--sage)" strokeWidth="1.5" strokeLinejoin="round" fill="rgba(var(--sage-rgb), 0.08)"/>
            <path d="M12 28h8" stroke="var(--sage)" strokeWidth="1.5" strokeLinecap="round"/>
          </svg>
          <span>No wiki pages yet</span>
          <span className="memex-empty-hint">Pages will appear here after the first Memex ingest runs.</span>
        </div>
      ) : (
        Array.from(grouped.entries())
          .sort(([a], [b]) => a.localeCompare(b))
          .map(([category, catPages]) => (
            <div key={category} className="memex-category-group">
              <h3 className="memex-category-label">{category}</h3>
              <div className="memex-card-grid">
                {catPages.map((page, i) => (
                  <section
                    key={page.path}
                    className="glass-card memex-page-card"
                    style={{ animationDelay: `${i * 0.03}s` }}
                    onClick={() => openPage(page.path)}
                  >
                    <div className="memex-card-header">
                      <h4 className="memex-card-title">{page.title}</h4>
                      {page.confidence != null && (
                        <span
                          className="memex-confidence memex-confidence--sm"
                          style={{ background: `${confidenceColor(page.confidence)}18`, color: confidenceColor(page.confidence) }}
                        >
                          {(page.confidence * 100).toFixed(0)}%
                        </span>
                      )}
                    </div>
                    <div className="memex-card-meta">
                      {page.last_updated && (
                        <span className="memex-card-date">{page.last_updated}</span>
                      )}
                    </div>
                  </section>
                ))}
              </div>
            </div>
          ))
      )}
      <div style={{ minHeight: 24, flexShrink: 0 }} />
    </div>
  );
}
