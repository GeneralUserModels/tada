import { useEffect, useRef, useState } from "react";
import { useAppContext } from "../../context/AppContext";
import { useSeeker } from "../../hooks/useSeeker";

function formatDate(date: string): string {
  // date is YYYYMMDD_HHMMSS or YYYYMMDD
  const m = date.match(/^(\d{4})(\d{2})(\d{2})(?:_(\d{2})(\d{2})(\d{2}))?$/);
  if (!m) return date;
  const d = new Date(+m[1], +m[2] - 1, +m[3], +(m[4] ?? 0), +(m[5] ?? 0));
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })
    + (m[4] ? ", " + d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" }) : "");
}

export function SeekerView() {
  const { state } = useAppContext();
  const {
    status,
    messages,
    streaming,
    loading,
    history,
    viewingFile,
    viewingMessages,
    loadStatus,
    loadConversation,
    loadHistory,
    viewPastConversation,
    clearViewing,
    startConversation,
    sendMessage,
    endConversation,
  } = useSeeker();
  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (state.connected) {
      loadStatus();
      loadConversation();
      loadHistory();
    }
  }, [state.connected, loadStatus, loadConversation, loadHistory]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, viewingMessages]);

  const handleSend = () => {
    const text = input.trim();
    if (!text || streaming) return;
    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
    sendMessage(text);
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    const el = e.target;
    el.style.height = "auto";
    const clamped = Math.min(el.scrollHeight, 120);
    el.style.height = clamped + "px";
    el.style.overflowY = el.scrollHeight > 120 ? "auto" : "hidden";
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  if (loading || !status) {
    return (
      <div id="seeker-view" className="view active">
        <div style={{ color: "var(--text-tertiary)", fontSize: 12, padding: 12 }}>Loading...</div>
      </div>
    );
  }

  // Viewing a past conversation read-only
  if (viewingFile) {
    return (
      <div id="seeker-view" className="view active">
        <div className="seeker-chat">
          <div className="seeker-history-bar">
            <button className="seeker-back-btn" onClick={clearViewing}>
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path d="M9 2L4 7l5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
              Back
            </button>
            <span className="seeker-history-date">{formatDate(viewingFile.replace("conversation_", "").replace(".md", ""))}</span>
          </div>
          <div className="seeker-messages">
            {viewingMessages.map((msg, i) => (
              <div key={i} className={`seeker-message seeker-message--${msg.role}`}>
                <div className="seeker-message-bubble">{msg.content}</div>
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>
        </div>
      </div>
    );
  }

  // Active conversation — chat UI
  if (status.conversation_active) {
    return (
      <div id="seeker-view" className="view active">
        <div className="seeker-chat">
          <div className="seeker-messages">
            {messages.map((msg, i) => (
              <div key={i} className={`seeker-message seeker-message--${msg.role}`}>
                <div className="seeker-message-bubble">
                  {msg.content || (streaming && i === messages.length - 1 ? <span className="seeker-typing" /> : null)}
                </div>
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>
          <div className="seeker-input-area">
            <textarea
              ref={textareaRef}
              className="seeker-input"
              value={input}
              onChange={handleInput}
              onKeyDown={handleKeyDown}
              placeholder="Type your response..."
              disabled={streaming}
              rows={1}
            />
            <button className="pill-btn pill-start" onClick={handleSend} disabled={streaming || !input.trim()}>
              Send
            </button>
            <button className="pill-btn pill-stop" onClick={endConversation} disabled={streaming}>
              End
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Not in a conversation — show status + history list
  return (
    <div id="seeker-view" className="view active">
      {/* Status card */}
      {status.has_questions && !status.questions_answered ? (
        <section className="glass-card seeker-status">
          <svg width="32" height="32" viewBox="0 0 32 32" fill="none" style={{ opacity: 0.5 }}>
            <circle cx="14" cy="14" r="9" stroke="var(--sage)" strokeWidth="2"/>
            <path d="M21 21L28 28" stroke="var(--sage)" strokeWidth="2" strokeLinecap="round"/>
          </svg>
          <p>New questions are ready based on your recent activity.</p>
          <button className="pill-btn pill-start" onClick={startConversation}>
            Start Conversation
          </button>
        </section>
      ) : (
        <section className="glass-card seeker-status">
          <svg width="32" height="32" viewBox="0 0 32 32" fill="none" style={{ opacity: 0.4 }}>
            <circle cx="16" cy="16" r="12" stroke="var(--sage)" strokeWidth="1.5" strokeDasharray="4 3"/>
          </svg>
          <p>Waiting for new questions...</p>
          <p style={{ fontSize: 11, color: "var(--text-tertiary)" }}>
            Seeker will generate personalized questions based on your activity.
          </p>
        </section>
      )}

      {/* Past conversations list */}
      {history.length > 0 && (
        <section className="glass-card seeker-history-section">
          <h3 className="seeker-history-title">Past Conversations</h3>
          <div className="seeker-history-list">
            {history.map((entry) => (
              <button
                key={entry.filename}
                className="seeker-history-item"
                onClick={() => viewPastConversation(entry.filename)}
              >
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                  <path d="M2 3.5h10M2 7h10M2 10.5h6" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
                </svg>
                <span>{formatDate(entry.date)}</span>
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none" style={{ marginLeft: "auto", opacity: 0.4 }}>
                  <path d="M4.5 2.5L8 6l-3.5 3.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </button>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
