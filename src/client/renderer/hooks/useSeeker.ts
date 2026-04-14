import { useState, useCallback, useEffect, useRef } from "react";
import { getSeekerStatus, getSeekerConversation, endSeekerConversation, getSeekerHistory, getSeekerPastConversation } from "../api/client";
import { getServerUrl } from "../../shared/api-core";
import { on as sseOn } from "../api/sse";
import { useAppContext } from "../context/AppContext";

export interface HistoryEntry {
  filename: string;
  date: string;
}

export function useSeeker() {
  const { dispatch } = useAppContext();
  const [status, setStatus] = useState<SeekerStatus | null>(null);
  const [messages, setMessages] = useState<SeekerMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [loading, setLoading] = useState(true);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [viewingFile, setViewingFile] = useState<string | null>(null);
  const [viewingMessages, setViewingMessages] = useState<SeekerMessage[]>([]);
  const abortRef = useRef<AbortController | null>(null);

  const loadStatus = useCallback(async () => {
    try {
      const s = await getSeekerStatus();
      setStatus(s);
      if (s.has_questions && !s.questions_answered) {
        dispatch({ type: "SEEKER_QUESTIONS_READY" });
      } else {
        dispatch({ type: "SEEKER_QUESTIONS_CLEARED" });
      }
    } catch (e) {
      console.error("[seeker] status load failed:", e);
    }
  }, [dispatch]);

  const loadConversation = useCallback(async () => {
    try {
      const conv = await getSeekerConversation();
      setMessages(conv.messages);
    } catch (e) {
      console.error("[seeker] conversation load failed:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadHistory = useCallback(async () => {
    try {
      const h = await getSeekerHistory();
      setHistory(h);
    } catch (e) {
      console.error("[seeker] history load failed:", e);
    }
  }, []);

  const viewPastConversation = useCallback(async (filename: string) => {
    try {
      const data = await getSeekerPastConversation(filename);
      setViewingFile(filename);
      setViewingMessages(data.messages);
    } catch (e) {
      console.error("[seeker] past conversation load failed:", e);
    }
  }, []);

  const clearViewing = useCallback(() => {
    setViewingFile(null);
    setViewingMessages([]);
  }, []);

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
        console.error("[seeker] stream error:", text);
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
            if (data.conversation_ended) {
              setMessages((prev) => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                updated[updated.length - 1] = {
                  ...last,
                  content: last.content.replace("[DONE]", "").trim(),
                };
                return updated;
              });
            }
            await loadStatus();
            await loadHistory();
          }
        }
      }
    } catch (e: unknown) {
      if (e instanceof Error && e.name === "AbortError") return;
      console.error("[seeker] stream error:", e);
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  }

  const startConversation = useCallback(async () => {
    setMessages([]);
    await streamResponse("/api/seeker/start");
    await loadStatus();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const sendMessage = useCallback(async (content: string) => {
    setMessages((prev) => [...prev, { role: "user", content }]);
    await streamResponse("/api/seeker/message", { content });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const endConversation = useCallback(async () => {
    if (abortRef.current) abortRef.current.abort();
    try {
      await endSeekerConversation();
    } catch (e) {
      console.error("[seeker] end failed:", e);
    }
    await loadStatus();
    await loadConversation();
    await loadHistory();
  }, [loadStatus, loadConversation, loadHistory]);

  useEffect(() => {
    sseOn("seeker_questions_ready", () => {
      loadStatus();
      loadConversation();
    });
    sseOn("seeker_conversation_ended", () => {
      loadStatus();
      loadConversation();
      loadHistory();
    });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return {
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
  };
}
