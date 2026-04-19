/**
 * ChatView — generic chat UI component.
 *
 * Renders message bubbles, input textarea, send/end buttons, typing indicator.
 * Reusable across seeker, moment feedback, chat app, etc.
 */

import { useEffect, useRef, useState } from "react";

export interface ChatViewProps {
  messages: ChatMessage[];
  streaming: boolean;
  active: boolean;
  onSend: (content: string) => void;
  onEnd?: () => void;
  placeholder?: string;
}

export function ChatView({ messages, streaming, active, onSend, onEnd, placeholder }: ChatViewProps) {
  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = () => {
    const text = input.trim();
    if (!text || streaming) return;
    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
    onSend(text);
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

  return (
    <div className="chat-container">
      <div className="chat-messages">
        {messages.map((msg, i) => (
          <div key={i} className={`chat-message chat-message--${msg.role}`}>
            <div className="chat-message-bubble">
              {msg.content || (streaming && i === messages.length - 1 ? <span className="chat-typing" /> : null)}
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>
      {active && (
        <div className="chat-input-area">
          <textarea
            ref={textareaRef}
            className="chat-input"
            value={input}
            onChange={handleInput}
            onKeyDown={handleKeyDown}
            placeholder={placeholder ?? "Type your response..."}
            disabled={streaming}
            rows={1}
          />
          <button className="pill-btn pill-start" onClick={handleSend} disabled={streaming || !input.trim()}>
            Send
          </button>
          {onEnd && (
            <button className="pill-btn pill-stop" onClick={onEnd} disabled={streaming}>
              End
            </button>
          )}
        </div>
      )}
    </div>
  );
}
