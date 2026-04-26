/**
 * useChatApp — chat-app hook with session list, draft mode, token streaming.
 *
 * Switching chats doesn't abort in-flight streams; only foreground tokens
 * update `items`. Stop targets the active session's controller.
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
import { useAppContext } from "../context/AppContext";

export function useChatApp() {
  const { dispatch } = useAppContext();
  const [sessions, setSessions] = useState<ChatSessionMeta[]>([]);
  const [activeId, setActiveIdState] = useState<string | null>(null);
  const [activeMeta, setActiveMeta] = useState<ChatSessionMeta | null>(null);
  const [items, setItems] = useState<ChatItem[]>([]);
  const [pendingSessions, setPendingSessions] = useState<Set<string>>(new Set());
  const [unreadSessions, setUnreadSessions] = useState<Set<string>>(new Set());
  const [options, setOptions] = useState<ChatOptions | null>(null);
  const [loadingSession, setLoadingSession] = useState(false);
  // Draft model+effort, used when no session is selected.
  const [draftModel, setDraftModel] = useState<string>("");
  const [draftEffort, setDraftEffort] = useState<string>("medium");

  // Sync mirror of activeId for SSE handlers running outside the render cycle.
  const activeIdRef = useRef<string | null>(null);
  useEffect(() => {
    activeIdRef.current = activeId;
  }, [activeId]);

  // Per-session AbortController so abort() and concurrent sends don't collide.
  const controllersRef = useRef<Map<string, AbortController>>(new Map());

  const streaming = activeId !== null && pendingSessions.has(activeId);

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
    setActiveIdState(null);
    setActiveMeta(null);
    setItems([]);
  }, []);

  const selectSession = useCallback(async (id: string | null) => {
    setActiveIdState(id);
    setItems([]);
    setActiveMeta(null);
    if (id) {
      setUnreadSessions((prev) => {
        if (!prev.has(id)) return prev;
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }
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
      const c = controllersRef.current.get(id);
      if (c) c.abort();
      controllersRef.current.delete(id);
      await deleteChatSession(id);
      setUnreadSessions((prev) => {
        if (!prev.has(id)) return prev;
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
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
      // If the active session already has a pending stream, ignore.
      if (activeId && pendingSessions.has(activeId)) return;

      // Lazy create on first message in a draft.
      let currentId = activeId;
      let currentMeta = activeMeta;
      if (!currentId) {
        const meta = await createChatSession({ model: draftModel, effort: draftEffort });
        currentId = meta.id;
        currentMeta = meta;
        // Only switch the user to the new session if they're still on the
        // draft. If they navigated away during the create await, leave them
        // alone — the new chat will appear in the sidebar via loadSessions.
        if (activeIdRef.current === null) {
          setActiveIdState(meta.id);
          // Update the ref synchronously so the immediately-following
          // foreground checks see the new session id without waiting on
          // React's render cycle.
          activeIdRef.current = meta.id;
          setActiveMeta(meta);
        }
      }
      const sessionId = currentId;

      // Render user msg only if still on this chat.
      if (sessionId === activeIdRef.current) {
        setItems((prev) => [...prev, { role: "user", content }]);
      }

      const controller = new AbortController();
      controllersRef.current.set(sessionId, controller);
      setPendingSessions((prev) => {
        const next = new Set(prev);
        next.add(sessionId);
        return next;
      });

      let gotTokensForCurrentRound = false;
      let finalBubbleEmitted = false;

      try {
        const res = await fetch(`${getServerUrl()}/api/chat/sessions/${sessionId}/message`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content }),
          signal: controller.signal,
        });
        if (!res.ok) {
          const text = await res.text();
          console.error("[chat] send failed:", text);
          return;
        }

        // Backend has already persisted the user message before the
        // StreamingResponse returns, so message_count is now >= 1 and the
        // new chat will pass the list_sessions filter. Refresh the sidebar
        // immediately so the chat shows up as "New chat" right away even if
        // the user has clicked away to another chat.
        loadSessions();

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

            // Only mutate items if this stream is for the active chat.
            const isForeground = sessionId === activeIdRef.current;

            if (typeof data.token === "string") {
              gotTokensForCurrentRound = true;
              if (isForeground) {
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
            }

            if (typeof data.round_end === "number") {
              const r = data.round_end;
              if (data.is_final) {
                if (gotTokensForCurrentRound) {
                  finalBubbleEmitted = true;
                  if (isForeground) {
                    setItems((prev) => {
                      const last = prev[prev.length - 1];
                      if (last && last.role === "assistant" && last.round === r) {
                        return [
                          ...prev.slice(0, -1),
                          { role: "assistant", content: last.content },
                        ];
                      }
                      return prev;
                    });
                  }
                }
              } else if (isForeground) {
                // Prelude — drop the tentative bubble.
                setItems((prev) => {
                  const last = prev[prev.length - 1];
                  if (last && last.role === "assistant" && last.round === r) {
                    return prev.slice(0, -1);
                  }
                  return prev;
                });
              }
              gotTokensForCurrentRound = false;
            }

            if (typeof data.final === "string") {
              if (!finalBubbleEmitted && data.final.trim()) {
                finalBubbleEmitted = true;
                if (isForeground) {
                  setItems((prev) => [
                    ...prev,
                    { role: "assistant", content: data.final },
                  ]);
                }
              }
            }

            if (typeof data.title === "string") {
              if (sessionId === activeIdRef.current) {
                setActiveMeta((prev) =>
                  prev ? { ...prev, title: data.title } : prev,
                );
              }
            }

            if (data.error && isForeground) {
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
        controllersRef.current.delete(sessionId);
        setPendingSessions((prev) => {
          if (!prev.has(sessionId)) return prev;
          const next = new Set(prev);
          next.delete(sessionId);
          return next;
        });
        loadSessions();
        if (sessionId === activeIdRef.current) {
          // User is still here — refresh from disk and don't mark unread.
          try {
            const data = await getChatSession(sessionId);
            setActiveMeta(data.meta);
            setItems(data.messages);
          } catch {
            /* sidebar refresh already covers it */
          }
        } else {
          // User navigated away — flag the chat as having a new response.
          setUnreadSessions((prev) => {
            const next = new Set(prev);
            next.add(sessionId);
            return next;
          });
        }
      }
      void currentMeta;
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [activeId, activeMeta, pendingSessions, draftModel, draftEffort, loadSessions],
  );

  const abort = useCallback(() => {
    if (!activeId) return;
    const c = controllersRef.current.get(activeId);
    if (c) c.abort();
    // Clear the activity pip immediately; backend will also clear on finally.
    dispatch({
      type: "AGENT_ACTIVITY",
      data: { agent: "chat", message: null },
    });
  }, [activeId, dispatch]);

  useEffect(() => {
    const controllers = controllersRef.current;
    return () => {
      // Abort all pending streams on unmount.
      controllers.forEach((c) => c.abort());
      controllers.clear();
    };
  }, []);

  return {
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
