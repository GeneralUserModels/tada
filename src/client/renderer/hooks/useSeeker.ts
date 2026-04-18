/**
 * useSeeker — seeker-specific hook built on top of useChat.
 *
 * Adds: status polling, conversation history, past conversation viewing,
 * SSE event listeners for seeker_questions_ready / seeker_conversation_ended.
 */

import { useState, useCallback, useEffect } from "react";
import { getSeekerStatus, getSeekerConversation, getSeekerHistory, getSeekerPastConversation } from "../api/client";
import { on as sseOn } from "../api/sse";
import { useAppContext } from "../context/AppContext";
import { useChat } from "./useChat";

export interface HistoryEntry {
  filename: string;
  date: string;
}

export function useSeeker() {
  const { dispatch } = useAppContext();
  const chat = useChat({ apiPrefix: "/api/seeker", doneMarker: "[DONE]" });
  const [status, setStatus] = useState<SeekerStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [viewingFile, setViewingFile] = useState<string | null>(null);
  const [viewingMessages, setViewingMessages] = useState<ChatMessage[]>([]);

  const loadStatus = useCallback(async () => {
    try {
      const s = await getSeekerStatus();
      setStatus(s);
      if (s.conversation_active) {
        chat.setActive(true);
      }
      if (s.has_questions && !s.questions_answered) {
        dispatch({ type: "SEEKER_QUESTIONS_READY" });
      } else {
        dispatch({ type: "SEEKER_QUESTIONS_CLEARED" });
      }
    } catch (e) {
      console.error("[seeker] status load failed:", e);
    }
  }, [dispatch, chat.setActive]); // eslint-disable-line react-hooks/exhaustive-deps

  const loadConversation = useCallback(async () => {
    try {
      const conv = await getSeekerConversation();
      chat.setMessages(conv.messages);
      chat.setActive(conv.active);
    } catch (e) {
      console.error("[seeker] conversation load failed:", e);
    } finally {
      setLoading(false);
    }
  }, [chat.setMessages, chat.setActive]); // eslint-disable-line react-hooks/exhaustive-deps

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
      // Skip the first message (initial "ask me whatever" prompt)
      const msgs = data.messages;
      setViewingMessages(msgs.length > 0 && msgs[0].role === "user" ? msgs.slice(1) : msgs);
    } catch (e) {
      console.error("[seeker] past conversation load failed:", e);
    }
  }, []);

  const clearViewing = useCallback(() => {
    setViewingFile(null);
    setViewingMessages([]);
  }, []);

  const startConversation = useCallback(async () => {
    await chat.startConversation();
    await loadStatus();
  }, [chat.startConversation, loadStatus]); // eslint-disable-line react-hooks/exhaustive-deps

  const endConversation = useCallback(async () => {
    await chat.endConversation();
    await loadStatus();
    await loadConversation();
    await loadHistory();
  }, [chat.endConversation, loadStatus, loadConversation, loadHistory]); // eslint-disable-line react-hooks/exhaustive-deps

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
    // Chat (generic)
    messages: chat.messages,
    streaming: chat.streaming,
    active: chat.active,
    sendMessage: chat.sendMessage,
    // Seeker-specific
    status,
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
    endConversation,
  };
}
