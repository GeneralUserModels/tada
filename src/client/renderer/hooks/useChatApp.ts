/**
 * useChatApp — chat-app hook with session list, draft mode, token streaming.
 *
 * Default state is a "draft" chat (no session id, model+effort selected). The
 * session is created lazily on the first sendMessage so empty drafts never
 * clutter the saved-sessions list.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { getServerUrl } from "../../shared/api-core";
import {
  createChatSession,
  deleteChatSession,
  getChatOptions,
  getChatSession,
  listChatSessions,
  updateChatSession,
} from "../api/client";

export function useChatApp() {
  const [sessions, setSessions] = useState<ChatSessionMeta[]>([]);
  const [activeId, setActiveIdState] = useState<string | null>(null);
  const [activeMeta, setActiveMeta] = useState<ChatSessionMeta | null>(null);
  const [items, setItems] = useState<ChatItem[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [options, setOptions] = useState<ChatOptions | null>(null);
  const [loadingSession, setLoadingSession] = useState(false);
  // Draft model+effort, used when no session is selected.
  const [draftModel, setDraftModel] = useState<string>("");
  const [draftEffort, setDraftEffort] = useState<string>("medium");
  const abortRef = useRef<AbortController | null>(null);

  const loadOptions = useCallback(async () => {
    const o = await getChatOptions();
    setOptions(o);
    setDraftModel((m) => m || o.default_model);
    setDraftEffort((e) => e || o.default_effort);
  }, []);

  const loadSessions = useCallback(async () => {
    const list = await listChatSessions();
    setSessions(list);
  }, []);

  const newDraft = useCallback(() => {
    if (abortRef.current) abortRef.current.abort();
    setActiveIdState(null);
    setActiveMeta(null);
    setItems([]);
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

  const setEffort = useCallback(
    async (effort: string) => {
      if (activeId && activeMeta) {
        const updated = await updateChatSession(activeId, { effort });
        setActiveMeta(updated);
        await loadSessions();
      } else {
        setDraftEffort(effort);
      }
    },
    [activeId, activeMeta, loadSessions],
  );

  const setModel = useCallback(
    async (model: string) => {
      if (!activeId) setDraftModel(model);
      // Mid-conversation model change is not supported (would need a new endpoint).
    },
    [activeId],
  );

  const sendMessage = useCallback(
    async (content: string) => {
      if (streaming) return;

      // Lazy create on first message in a draft
      let currentId = activeId;
      let currentMeta = activeMeta;
      if (!currentId) {
        const meta = await createChatSession({ model: draftModel, effort: draftEffort });
        currentId = meta.id;
        currentMeta = meta;
        setActiveIdState(meta.id);
        setActiveMeta(meta);
      }

      const userItem: ChatItem = { role: "user", content };
      setItems((prev) => [...prev, userItem]);
      setStreaming(true);

      const controller = new AbortController();
      abortRef.current = controller;

      // Stream every round's tokens into a *tentative* assistant bubble in
      // `items` (rendered as a normal markdown bubble). round_end then either
      // makes it permanent (final round) or removes it (prelude).
      // Tentative bubbles carry a `round` field; permanent ones don't.
      let promotedFinal = false;

      try {
        const res = await fetch(`${getServerUrl()}/api/chat/sessions/${currentId}/message`, {
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

            if (typeof data.token === "string") {
              const round = data.round ?? 0;
              setItems((prev) => {
                const last = prev[prev.length - 1];
                if (last && last.role === "assistant" && last.round === round) {
                  return [
                    ...prev.slice(0, -1),
                    { ...last, content: last.content + data.token },
                  ];
                }
                return [
                  ...prev,
                  { role: "assistant", content: data.token, round },
                ];
              });
            }

            if (typeof data.round_end === "number") {
              const r = data.round_end;
              if (data.is_final) {
                // Promote tentative → permanent (drop the round flag).
                setItems((prev) => {
                  const last = prev[prev.length - 1];
                  if (last && last.role === "assistant" && last.round === r && last.content.trim()) {
                    promotedFinal = true;
                    return [
                      ...prev.slice(0, -1),
                      { role: "assistant", content: last.content },
                    ];
                  }
                  return prev;
                });
              } else {
                // Prelude — drop the tentative bubble. The agent's narration
                // (if any leaked through despite the prompt) was just status.
                setItems((prev) => {
                  const last = prev[prev.length - 1];
                  if (last && last.role === "assistant" && last.round === r) {
                    return prev.slice(0, -1);
                  }
                  return prev;
                });
              }
            }

            if (typeof data.final === "string") {
              // Backstop: if streaming produced no tokens at all (e.g. the
              // provider didn't stream content), surface the final text now.
              if (!promotedFinal && data.final.trim()) {
                setItems((prev) => [
                  ...prev,
                  { role: "assistant", content: data.final },
                ]);
                promotedFinal = true;
              }
            }

            if (typeof data.title === "string" && currentMeta) {
              currentMeta = { ...currentMeta, title: data.title };
              setActiveMeta(currentMeta);
            }

            if (data.error) {
              setItems((prev) => [
                ...prev,
                { role: "assistant", content: `**Error:** ${data.error}` },
              ]);
            }
          }
        }
      } catch (e: unknown) {
        if (e instanceof Error && e.name === "AbortError") return;
        console.error("[chat] stream error:", e);
      } finally {
        setStreaming(false);
        abortRef.current = null;
        loadSessions();
      }
    },
    [activeId, activeMeta, streaming, draftModel, draftEffort, loadSessions],
  );

  const abort = useCallback(() => {
    if (abortRef.current) abortRef.current.abort();
  }, []);

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
    draftModel,
    draftEffort,
    loadOptions,
    loadSessions,
    selectSession,
    newDraft,
    removeSession,
    sendMessage,
    setEffort,
    setModel,
    abort,
  };
}
