/**
 * useChat — generic hook for streaming chat with a backend agent.
 *
 * Handles SSE streaming, message accumulation, and done-marker stripping.
 * Each app (seeker, moment feedback, chat) configures its own apiPrefix.
 */

import { useState, useCallback, useEffect, useRef } from "react";
import { getServerUrl } from "../../shared/api-core";

export interface UseChatConfig {
  apiPrefix: string; // e.g. "/api/seeker"
  doneMarker?: string; // e.g. "[DONE]" — stripped from display
}

export function useChat(config: UseChatConfig) {
  const { apiPrefix, doneMarker } = config;
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [active, setActive] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  // Reset state when apiPrefix changes (e.g. switching between moments)
  useEffect(() => {
    if (abortRef.current) abortRef.current.abort();
    abortRef.current = null;
    setMessages([]);
    setStreaming(false);
    setActive(false);
  }, [apiPrefix]);

  async function streamResponse(path: string, body?: unknown) {
    setStreaming(true);
    setMessages((prev) => [...prev, { role: "assistant", content: "" }]);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const res = await fetch(`${getServerUrl()}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: body ? JSON.stringify(body) : undefined,
        signal: controller.signal,
      });

      if (!res.ok) {
        const text = await res.text();
        console.error("[chat] stream error:", text);
        setMessages((prev) => prev.slice(0, -1));
        setStreaming(false);
        return;
      }

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop()!;

        for (const part of parts) {
          const line = part.trim();
          if (!line.startsWith("data: ")) continue;
          const data = JSON.parse(line.slice(6));

          if (data.token) {
            setMessages((prev) => {
              const updated = [...prev];
              const last = updated[updated.length - 1];
              updated[updated.length - 1] = { ...last, content: last.content + data.token };
              return updated;
            });
          }

          if (data.done) {
            if (data.conversation_ended && doneMarker) {
              setMessages((prev) => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                updated[updated.length - 1] = {
                  ...last,
                  content: last.content.replace(doneMarker, "").trim(),
                };
                return updated;
              });
              setActive(false);
            }
          }
        }
      }
    } catch (e: unknown) {
      if (e instanceof Error && e.name === "AbortError") return;
      console.error("[chat] stream error:", e);
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  }

  const startConversation = useCallback(async (initialMessage?: string) => {
    setMessages(initialMessage ? [{ role: "user", content: initialMessage }] : []);
    setActive(true);
    const body = initialMessage ? { content: initialMessage } : undefined;
    await streamResponse(`${apiPrefix}/start`, body);
  }, [apiPrefix]); // eslint-disable-line react-hooks/exhaustive-deps

  const sendMessage = useCallback(
    async (content: string) => {
      setMessages((prev) => [...prev, { role: "user", content }]);
      await streamResponse(`${apiPrefix}/message`, { content });
    },
    [apiPrefix], // eslint-disable-line react-hooks/exhaustive-deps
  );

  const endConversation = useCallback(async () => {
    if (abortRef.current) abortRef.current.abort();
    try {
      await fetch(`${getServerUrl()}${apiPrefix}/end`, { method: "POST" });
    } catch (e) {
      console.error("[chat] end failed:", e);
    }
    setActive(false);
  }, [apiPrefix]);

  const abort = useCallback(() => {
    if (abortRef.current) abortRef.current.abort();
  }, []);

  return {
    messages,
    setMessages,
    streaming,
    active,
    setActive,
    startConversation,
    sendMessage,
    endConversation,
    abort,
  };
}
