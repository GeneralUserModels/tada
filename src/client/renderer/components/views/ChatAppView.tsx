/**
 * ChatAppView — general-purpose assistant chat with persistent sessions.
 *
 * Two-pane layout: left = session list, right = active chat with
 * markdown-rendered messages and live tool-action chips.
 */

import React, { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";

import { useAppContext } from "../../context/AppContext";
import { useChatApp } from "../../hooks/useChatApp";
import { FeatureActivityBanner } from "../FeatureActivityBanner";

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

function StepChip({ summary }: { summary: string }) {
  return (
    <div className="chat-step-chip">
      <svg width="11" height="11" viewBox="0 0 12 12" fill="none">
        <path d="M6 1v3M6 8v3M1 6h3M8 6h3M2.5 2.5l2 2M7.5 7.5l2 2M2.5 9.5l2-2M7.5 4.5l2-2"
          stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
      </svg>
      <span>{summary}</span>
    </div>
  );
}

function MessageBubble({ item }: { item: ChatBubbleItem }) {
  return (
    <div className={`chat-message chat-message--${item.role}`}>
      <div className="chat-message-bubble">
        {item.role === "assistant" ? (
          <div className="chat-markdown">
            <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]}>
              {item.content}
            </ReactMarkdown>
          </div>
        ) : (
          item.content
        )}
      </div>
    </div>
  );
}

function NewChatForm({
  options,
  onCreate,
  onCancel,
}: {
  options: ChatOptions;
  onCreate: (body: { model: string; effort: string }) => void;
  onCancel: () => void;
}) {
  const [model, setModel] = useState(options.default_model);
  const [effort, setEffort] = useState<string>(options.default_effort);
  return (
    <div className="chat-new-form glass-card">
      <label>
        <span>Model</span>
        <select value={model} onChange={(e) => setModel(e.target.value)}>
          {options.models.map((m) => (
            <option key={m} value={m}>{m}</option>
          ))}
        </select>
      </label>
      <label>
        <span>Effort</span>
        <select value={effort} onChange={(e) => setEffort(e.target.value)}>
          {options.efforts.map((eff) => (
            <option key={eff} value={eff}>
              {EFFORT_LABELS[eff] ?? eff} · {options.effort_max_rounds[eff]} turns
            </option>
          ))}
        </select>
      </label>
      <div className="chat-new-form-actions">
        <button className="pill-btn pill-start" onClick={() => onCreate({ model, effort })}>
          Start chat
        </button>
        <button className="pill-btn pill-stop" onClick={onCancel}>
          Cancel
        </button>
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
    loadOptions,
    loadSessions,
    selectSession,
    createSession,
    removeSession,
    sendMessage,
  } = useChatApp();

  const [input, setInput] = useState("");
  const [showNewForm, setShowNewForm] = useState(false);
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
    if (!text || streaming || !activeId) return;
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

  return (
    <div id="chat-view" className="view active chat-app">
      {/* Left pane — session list */}
      <aside className="chat-app-sidebar">
        <button
          className="chat-app-new-btn"
          onClick={() => {
            setShowNewForm(true);
            selectSession(null);
          }}
        >
          + New chat
        </button>
        <div className="chat-app-sessions">
          {sessions.length === 0 && !showNewForm && (
            <div className="chat-app-empty-list">No chats yet.</div>
          )}
          {sessions.map((s) => (
            <div
              key={s.id}
              className={`chat-app-session-item${activeId === s.id ? " active" : ""}`}
              onClick={() => {
                setShowNewForm(false);
                selectSession(s.id);
              }}
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

      {/* Right pane — active chat / welcome / new-form */}
      <section className="chat-app-main">
        {chatActivity && <FeatureActivityBanner activity={chatActivity} label="Assistant" />}

        {showNewForm && options ? (
          <div className="chat-app-welcome">
            <NewChatForm
              options={options}
              onCreate={async (body) => {
                setShowNewForm(false);
                await createSession(body);
              }}
              onCancel={() => setShowNewForm(false)}
            />
          </div>
        ) : !activeId ? (
          <div className="chat-app-welcome">
            <div className="chat-welcome-card glass-card">
              <h2>Hi — I'm your assistant.</h2>
              <p>
                Ask me anything about your day, your week, or what I've seen across your apps.
                I can read your activity logs, files, and the web to answer.
              </p>
              <p>
                Or tell me about yourself — your role, what you're working on, preferences —
                and I'll use that to be more helpful.
              </p>
              <button
                className="pill-btn pill-start"
                onClick={() => setShowNewForm(true)}
              >
                Start a chat
              </button>
            </div>
          </div>
        ) : (
          <>
            {activeMeta && (
              <div className="chat-app-header">
                <div className="chat-app-title">{activeMeta.title}</div>
                <div className="chat-app-header-meta">
                  <span className="chat-badge">{activeMeta.model.split("/").pop()}</span>
                  <span className="chat-badge chat-badge--effort">
                    {EFFORT_LABELS[activeMeta.effort] ?? activeMeta.effort}
                  </span>
                </div>
              </div>
            )}
            <div className="chat-app-messages">
              {loadingSession && (
                <div className="chat-app-loading">Loading…</div>
              )}
              {items.length === 0 && !loadingSession && (
                <div className="chat-app-empty-thread">
                  Send a message to get started.
                </div>
              )}
              {items.map((item, i) =>
                item.role === "step" ? (
                  <StepChip key={i} summary={item.summary} />
                ) : (
                  <MessageBubble key={i} item={item} />
                ),
              )}
              {streaming && (
                <div className="chat-message chat-message--assistant">
                  <div className="chat-message-bubble">
                    <span className="chat-typing" />
                  </div>
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
              <button
                className="pill-btn pill-start"
                onClick={handleSend}
                disabled={streaming || !input.trim()}
              >
                Send
              </button>
            </div>
          </>
        )}
      </section>
    </div>
  );
}
