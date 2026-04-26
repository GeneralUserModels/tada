/**
 * ChatProvider — keeps the chat hook (useChatApp) mounted at App level so
 * in-flight streams, per-session state, and unread/pending tracking survive
 * view switches (Tada, Memex, etc.). Components consume via useChat().
 */

import React, { createContext, useContext, ReactNode } from "react";
import { useChatApp } from "../hooks/useChatApp";

type ChatValue = ReturnType<typeof useChatApp>;

const ChatContext = createContext<ChatValue | null>(null);

export function ChatProvider({ children }: { children: ReactNode }) {
  const value = useChatApp();
  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>;
}

export function useChat(): ChatValue {
  const ctx = useContext(ChatContext);
  if (!ctx) throw new Error("useChat must be used within ChatProvider");
  return ctx;
}
