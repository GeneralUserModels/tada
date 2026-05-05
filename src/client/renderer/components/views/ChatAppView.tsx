/**
 * ChatAppView — assistant chat with persistent sessions.
 *
 * Two-pane layout: left = saved sessions, right = active chat (or a fresh
 * draft if nothing is selected). The default landing state is a draft chat
 * with the input box ready and the welcome text in the empty thread area.
 */

import React, { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";

import { useAppContext } from "../../context/AppContext";
import { useChat } from "../../context/ChatContext";
import { FeatureActivityBanner } from "../FeatureActivityBanner";
import { SimpleDropdown, type DropdownOption } from "../shared/SimpleDropdown";
import { AGENT_MODELS } from "../shared/ModelDropdown";

const EFFORT_LABELS: Record<string, string> = { low: "Low", medium: "Medium", high: "High" };

const MODEL_LABELS: Record<string, string> = Object.fromEntries(
  AGENT_MODELS.map((m) => [m.value, m.label]),
);
const modelLabel = (m: string) => MODEL_LABELS[m] ?? m.split("/").pop() ?? m;

const WELCOME_SUGGESTIONS = [
  "Catch me up on my week",
  "What's on my schedule today?",
  "What have I been working on lately?",
];

function formatRelative(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  const now = Date.now();
  const diffMs = now - d.getTime();
  const mins = Math.round(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 7) return `${days}d ago`;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function MessageBubble({ item }: { item: ChatBubbleItem }) {
  return (
    <div className={`chat-message chat-message--${item.role}`}>
      <div className="chat-message-bubble">
        {item.role === "assistant" ? (
          <div className="chat-markdown">
            <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]}>
              {item.content || ""}
            </ReactMarkdown>
          </div>
        ) : (
          item.content
        )}
      </div>
    </div>
  );
}

export function ChatAppView() {
  const { state } = useAppContext();
  const chatActivity = state.agentActivities["chat"];
  const {
    sessions,
    activeId,
    activeMeta,
    items,
    streaming,
    pendingSessions,
    unreadSessions,
    options,
    loadingSession,
    draftModel,
    draftEffort,
    selectSession,
    newDraft,
    removeSession,
    sendMessage,
    setEffort,
    setModel,
    abort,
  } = useChat();

  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Per-session unsent-text drafts. Keyed by session id; the special key
  // "__draft__" holds the no-active-session (new chat) draft.
  const inputDraftsRef = useRef<Map<string, string>>(new Map());
  const inputRef = useRef("");
  const prevActiveIdRef = useRef<string | null | undefined>(undefined);

  // Smooth scroll only on incremental updates (typing, streaming, send).
  // Loading a past chat or switching chats jumps the length by more than 1
  // (or shrinks it to []), so use instant auto-scroll there.
  const lastItemsLengthRef = useRef(0);
  useEffect(() => {
    const prev = lastItemsLengthRef.current;
    const delta = items.length - prev;
    const behavior: ScrollBehavior =
      delta > 1 || delta < 0 ? "auto" : "smooth";
    messagesEndRef.current?.scrollIntoView({ behavior });
    lastItemsLengthRef.current = items.length;
  }, [items]);

  // Save the previous chat's typed text and restore the new chat's typed text
  // whenever the user switches between chats / drafts.
  useEffect(() => {
    if (prevActiveIdRef.current !== undefined) {
      const prevKey = prevActiveIdRef.current ?? "__draft__";
      inputDraftsRef.current.set(prevKey, inputRef.current);
    }
    const newKey = activeId ?? "__draft__";
    const restored = inputDraftsRef.current.get(newKey) ?? "";
    setInput(restored);
    inputRef.current = restored;
    prevActiveIdRef.current = activeId;

    // Re-fit textarea height to the restored content (clearing any inline
    // height left behind by the previous chat's auto-resize logic).
    setTimeout(() => {
      const el = textareaRef.current;
      if (!el) return;
      el.style.height = "auto";
      const clamped = Math.min(el.scrollHeight, 200);
      el.style.height = clamped + "px";
      el.style.overflowY = el.scrollHeight > 200 ? "auto" : "hidden";
    }, 0);
  }, [activeId]);

  const handleSend = () => {
    const text = input.trim();
    if (!text || streaming) return;
    setInput("");
    inputRef.current = "";
    // Clear the saved draft for this session — the message has been sent.
    const key = activeId ?? "__draft__";
    inputDraftsRef.current.delete(key);
    if (textareaRef.current) textareaRef.current.style.height = "auto";
    sendMessage(text);
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    inputRef.current = e.target.value;
    const el = e.target;
    el.style.height = "auto";
    const clamped = Math.min(el.scrollHeight, 200);
    el.style.height = clamped + "px";
    el.style.overflowY = el.scrollHeight > 200 ? "auto" : "hidden";
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const headerModel = activeMeta?.model ?? draftModel;
  const headerEffort = activeMeta?.effort ?? draftEffort;
  const headerTitle = activeMeta?.title ?? "New chat";

  return (
    <div id="chat-view" className="view active chat-app">
      {/* Left pane — session list */}
      <aside className="chat-app-sidebar">
        <button className="chat-app-new-btn" onClick={newDraft}>
          + New chat
        </button>
        <div className="chat-app-sessions">
          {sessions.length === 0 && (
            <div className="chat-app-empty-list">No saved chats yet.</div>
          )}
          {sessions.map((s) => {
            const isPending = pendingSessions.has(s.id);
            const isUnread = !isPending && unreadSessions.has(s.id);
            return (
            <div
              key={s.id}
              className={`chat-app-session-item${activeId === s.id ? " active" : ""}`}
              onClick={() => selectSession(s.id)}
            >
              <div className="chat-app-session-title-row">
                <span className="chat-app-session-title">{s.title || "Untitled"}</span>
                {isPending && <span className="nav-activity-spinner chat-app-session-indicator" />}
                {isUnread && <span className="tada-unread-dot chat-app-session-indicator" />}
              </div>
              <div className="chat-app-session-meta">
                <span>{formatRelative(s.updated_at)}</span>
                <span className="dot">·</span>
                <span>{EFFORT_LABELS[s.effort] ?? s.effort}</span>
              </div>
              <button
                className="chat-app-session-delete"
                title="Delete"
                onClick={(e) => {
                  e.stopPropagation();
                  if (confirm("Delete this chat?")) removeSession(s.id);
                }}
              >
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                  <path d="M3 3l6 6M9 3l-6 6" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
                </svg>
              </button>
            </div>
            );
          })}
        </div>
      </aside>

      {/* Right pane — active chat (or draft) */}
      <section className="chat-app-main">
        <div className="chat-app-header">
          <div className="chat-app-title">{headerTitle}</div>
          <div className="chat-app-header-meta">
            {options?.models && options.models.length > 1 ? (
              <SimpleDropdown<string>
                className="chat-model-dropdown"
                value={headerModel}
                options={options.models.map<DropdownOption<string>>((m) => ({
                  value: m,
                  label: modelLabel(m),
                }))}
                onChange={(v) => setModel(v)}
                disabled={!!activeId}
                title={activeId ? "Model can't be changed mid-conversation" : undefined}
              />
            ) : (
              <span className="chat-badge">{modelLabel(headerModel)}</span>
            )}
            <SimpleDropdown<string>
              className={`chat-effort-dropdown chat-effort-dropdown--${headerEffort}`}
              value={headerEffort}
              options={(options?.efforts ?? ["low", "medium", "high"]).map<DropdownOption<string>>((eff) => ({
                value: eff,
                label: EFFORT_LABELS[eff] ?? eff,
              }))}
              onChange={(v) => setEffort(v)}
              title={
                options
                  ? `Max output tokens: ${options.effort_max_tokens[headerEffort]?.toLocaleString() ?? "?"}`
                  : undefined
              }
            />
          </div>
        </div>

        <div className="chat-app-messages">
          {loadingSession && <div className="chat-app-loading">Loading…</div>}
          {!loadingSession && items.length === 0 && (
            <div className="chat-welcome-thread">
              <div className="chat-welcome-glow" aria-hidden="true" />
              <div className="chat-welcome-icon" aria-hidden="true">
                <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
                  <path
                    d="M5 9a3 3 0 0 1 3-3h14a3 3 0 0 1 3 3v8a3 3 0 0 1-3 3h-7l-5 4v-4H8a3 3 0 0 1-3-3V9z"
                    stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"
                  />
                  <circle cx="11" cy="13" r="1.2" fill="currentColor" />
                  <circle cx="15" cy="13" r="1.2" fill="currentColor" />
                  <circle cx="19" cy="13" r="1.2" fill="currentColor" />
                </svg>
              </div>
              <h2 className="chat-welcome-title">Ask me anything.</h2>
              <p className="chat-welcome-sub">
                I'll personalize answers using your activity logs and the live web.
              </p>
              <p className="chat-welcome-sub chat-welcome-sub--muted">
                Tell me about yourself any time and I'll use it to be more helpful.
              </p>
              <div className="chat-welcome-suggestions">
                {WELCOME_SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    type="button"
                    className="chat-welcome-chip"
                    onClick={() => {
                      setInput(s);
                      textareaRef.current?.focus();
                    }}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}
          {items.map((item, i) => (
            <MessageBubble key={i} item={item as ChatBubbleItem} />
          ))}
          {streaming && items.length > 0 && items[items.length - 1]?.role === "user" && (
            <div className="chat-inline-activity" aria-live="polite">
              {chatActivity ? (
                <FeatureActivityBanner activity={chatActivity} label="" />
              ) : (
                <div className="feature-activity-banner">
                  <div className="feature-activity-row">
                    <div className="feature-activity-spinner" />
                    <span className="feature-activity-text">Working…</span>
                  </div>
                </div>
              )}
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        <div className="chat-input-area">
          <textarea
            ref={textareaRef}
            className="chat-input"
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            placeholder="Ask anything…"
            rows={1}
          />
          {streaming ? (
            <button className="pill-btn pill-stop" onClick={abort}>
              Stop
            </button>
          ) : (
            <button
              className="pill-btn pill-start"
              onClick={handleSend}
              disabled={!input.trim()}
            >
              Send
            </button>
          )}
        </div>
      </section>
    </div>
  );
}
