import { useEffect, useRef, useState } from "react";

import { askChat, chatErrorMessage, trimChatHistory } from "../api/chat";

const CHAT_GREETING = "Hey there! I'm Foodie, your NTU campus food guide 🍜 Ask me about canteens, opening hours, or what's good today!";

type ChatHistoryMessage = {
  role: "user" | "assistant";
  content: string;
};

export type ChatUiMessage = {
  role: "user" | "bot";
  text: string;
  sources?: unknown[];
};

function createChatSessionId() {
  return globalThis.crypto?.randomUUID?.()
    ?? `chat-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function initialChatMessages(): ChatUiMessage[] {
  return [{ role: "bot", text: CHAT_GREETING }];
}

export function useChatSession() {
  const [messages, setMessages] = useState<ChatUiMessage[]>(initialChatMessages);
  const [input, setInput] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const requestPendingRef = useRef(false);
  const historyRef = useRef<ChatHistoryMessage[]>([]);
  const sessionIdRef = useRef("");
  const activeControllerRef = useRef<AbortController | null>(null);
  const requestIdRef = useRef(0);

  if (!sessionIdRef.current) sessionIdRef.current = createChatSessionId();

  useEffect(() => () => activeControllerRef.current?.abort(), []);

  async function sendMessage(text: string) {
    const question = text.trim();
    if (!question || requestPendingRef.current) return;

    const controller = new AbortController();
    const requestId = ++requestIdRef.current;
    const historyForRequest = historyRef.current;
    activeControllerRef.current = controller;
    requestPendingRef.current = true;
    historyRef.current = trimChatHistory([
      ...historyForRequest,
      { role: "user", content: question },
    ]);
    setMessages((previous) => [...previous, { role: "user", text: question }]);
    setInput("");
    setIsGenerating(true);

    try {
      const response = await askChat(question, {
        history: historyForRequest,
        sessionId: sessionIdRef.current,
        signal: controller.signal,
      });
      if (controller.signal.aborted || requestId !== requestIdRef.current) return;
      historyRef.current = trimChatHistory([
        ...historyRef.current,
        { role: "assistant", content: response.answer },
      ]);
      setMessages((previous) => [
        ...previous,
        { role: "bot", text: response.answer, sources: response.sources },
      ]);
    } catch (error) {
      if (controller.signal.aborted || requestId !== requestIdRef.current) return;
      console.error("Chat request failed", error);
      setMessages((previous) => [
        ...previous,
        { role: "bot", text: chatErrorMessage(error) },
      ]);
    } finally {
      if (requestId === requestIdRef.current) {
        activeControllerRef.current = null;
        requestPendingRef.current = false;
        setIsGenerating(false);
      }
    }
  }

  function stopResponse() {
    if (!requestPendingRef.current) return;
    requestIdRef.current += 1;
    activeControllerRef.current?.abort();
    activeControllerRef.current = null;
    requestPendingRef.current = false;
    setIsGenerating(false);
  }

  function startNewSession() {
    stopResponse();
    historyRef.current = [];
    sessionIdRef.current = createChatSessionId();
    setMessages(initialChatMessages());
    setInput("");
  }

  return {
    input,
    isGenerating,
    messages,
    sendMessage,
    setInput,
    startNewSession,
    stopResponse,
  };
}
