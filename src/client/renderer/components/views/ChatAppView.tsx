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
import { useChatApp } from "../../hooks/useChatApp";
import { FeatureActivityBanner } from "../FeatureActivityBanner";
import { SimpleDropdown, type DropdownOption } from "../shared/SimpleDropdown";

const EFFORT_LABELS: Record<string, string> = { low: "Low", medium: "Medium", high: "High" };

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
    options,
    loadingSession,
    draftModel,
    draftEffort,
    loadOptions,
    loadSessions,
    selectSession,
    newDraft,
    removeSession,
    sendMessage,
    setEffort,
    abort,
  } = useChatApp();

  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (state.connected) {
      loadOptions();
      loadSessions();
    }
  }, [state.connected, loadOptions, loadSessions]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [items]);

  const handleSend = () => {
    const text = input.trim();
    if (!text || streaming) return;
    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
    sendMessage(text);
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    const el = e.target;
    el.style.height = "auto";
    const clamped = Math.min(el.scrollHeight, 160);
    el.style.height = clamped + "px";
    el.style.overflowY = el.scrollHeight > 160 ? "auto" : "hidden";
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
          {sessions.map((s) => (
            <div
              key={s.id}
              className={`chat-app-session-item${activeId === s.id ? " active" : ""}`}
              onClick={() => selectSession(s.id)}
            >
              <div className="chat-app-session-title">{s.title || "Untitled"}</div>
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
          ))}
        </div>
      </aside>

      {/* Right pane — active chat (or draft) */}
      <section className="chat-app-main">
        <div className="chat-app-header">
          <div className="chat-app-title">{headerTitle}</div>
          <div className="chat-app-header-meta">
            <span className="chat-badge">{headerModel.split("/").pop()}</span>
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
              <h2>Ask me anything.</h2>
              <p>I'll personalize answers using your activity logs and the live web.</p>
              <p>Tell me about yourself any time and I'll use it to be more helpful.</p>
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
            disabled={streaming}
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
