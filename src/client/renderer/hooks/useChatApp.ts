/**
 * useChatApp — chat-app hook with session list management and SSE streaming
 * that handles {step}/{token}/{done} events from /api/chat.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { getServerUrl } from "../../shared/api-core";
import {
  createChatSession,
  deleteChatSession,
  getChatOptions,
  getChatSession,
  listChatSessions,
} from "../api/client";

export function useChatApp() {
  const [sessions, setSessions] = useState<ChatSessionMeta[]>([]);
  const [activeId, setActiveIdState] = useState<string | null>(null);
  const [activeMeta, setActiveMeta] = useState<ChatSessionMeta | null>(null);
  const [items, setItems] = useState<ChatItem[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [options, setOptions] = useState<ChatOptions | null>(null);
  const [loadingSession, setLoadingSession] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const loadOptions = useCallback(async () => {
    const o = await getChatOptions();
    setOptions(o);
  }, []);

  const loadSessions = useCallback(async () => {
    const list = await listChatSessions();
    setSessions(list);
  }, []);

  const selectSession = useCallback(async (id: string | null) => {
    if (abortRef.current) abortRef.current.abort();
    setActiveIdState(id);
    setItems([]);
    setActiveMeta(null);
    if (!id) return;
    setLoadingSession(true);
    try {
      const data = await getChatSession(id);
      setActiveMeta(data.meta);
      setItems(data.messages);
    } finally {
      setLoadingSession(false);
    }
  }, []);

  const createSession = useCallback(
    async (body: { model: string; effort: string; title?: string }) => {
      const meta = await createChatSession(body);
      await loadSessions();
      await selectSession(meta.id);
      return meta;
    },
    [loadSessions, selectSession],
  );

  const removeSession = useCallback(
    async (id: string) => {
      await deleteChatSession(id);
      if (activeId === id) {
        setActiveIdState(null);
        setActiveMeta(null);
        setItems([]);
      }
      await loadSessions();
    },
    [activeId, loadSessions],
  );

  const sendMessage = useCallback(
    async (content: string) => {
      if (!activeId || streaming) return;
      const userItem: ChatItem = { role: "user", content };
      setItems((prev) => [...prev, userItem]);
      setStreaming(true);

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const res = await fetch(`${getServerUrl()}/api/chat/sessions/${activeId}/message`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content }),
          signal: controller.signal,
        });
        if (!res.ok) {
          const text = await res.text();
          console.error("[chat] send failed:", text);
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
            if (data.step) {
              const step: ChatItem = {
                role: "step",
                tool: data.step.tool,
                summary: data.step.summary,
              };
              setItems((prev) => [...prev, step]);
            }
            if (typeof data.token === "string") {
              const reply: ChatItem = { role: "assistant", content: data.token };
              setItems((prev) => [...prev, reply]);
            }
            if (data.error) {
              const reply: ChatItem = {
                role: "assistant",
                content: `**Error:** ${data.error}`,
              };
              setItems((prev) => [...prev, reply]);
            }
          }
        }
      } catch (e: unknown) {
        if (e instanceof Error && e.name === "AbortError") return;
        console.error("[chat] stream error:", e);
      } finally {
        setStreaming(false);
        abortRef.current = null;
        // Refresh meta (updated_at, message_count) so the session list shows recency
        loadSessions();
      }
    },
    [activeId, streaming, loadSessions],
  );

  useEffect(() => {
    return () => {
      if (abortRef.current) abortRef.current.abort();
    };
  }, []);

  return {
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
  };
}
