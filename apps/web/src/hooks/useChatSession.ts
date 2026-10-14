import { useEffect, useRef, useState } from "react";

import { chatErrorMessage, streamChat, trimChatHistory } from "../api/chat";
import { useAuth } from "../contexts/AuthContext";

const ANONYMOUS_CHAT_GREETING = "Hey there! I'm Foodie, your NTU campus food guide 🍜 Ask me about canteens, opening hours, or what's good today!";

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

function initialChatMessages(displayName: string | null): ChatUiMessage[] {
  const greeting = displayName
    ? `Hey ${displayName}! I'm Foodie, your NTU campus food guide 🍜 Ask me about canteens, opening hours, or what's good today!`
    : ANONYMOUS_CHAT_GREETING;
  return [{ role: "bot", text: greeting }];
}

export function useChatSession() {
  const { user } = useAuth();
  const metadataDisplayName = typeof user?.user_metadata?.display_name === "string"
    && user.user_metadata.display_name.trim()
    ? user.user_metadata.display_name.trim()
    : null;
  const displayName = metadataDisplayName ?? user?.email ?? null;
  const [messages, setMessages] = useState<ChatUiMessage[]>(
    () => initialChatMessages(displayName),
  );
  const [input, setInput] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const requestPendingRef = useRef(false);
  const historyRef = useRef<ChatHistoryMessage[]>([]);
  const sessionIdRef = useRef("");
  const activeControllerRef = useRef<AbortController | null>(null);
  const requestIdRef = useRef(0);

  if (!sessionIdRef.current) sessionIdRef.current = createChatSessionId();

  useEffect(() => {
    setMessages((current) => (
      current.length === 1 && current[0].role === "bot"
        ? initialChatMessages(displayName)
        : current
    ));
  }, [displayName]);

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

    let hasStreamMessage = false;
    try {
      const response = await streamChat(question, {
        history: historyForRequest,
        sessionId: sessionIdRef.current,
        signal: controller.signal,
        onDelta: (_delta: string, answer: string) => {
          if (controller.signal.aborted || requestId !== requestIdRef.current) return;
          const shouldAppend = !hasStreamMessage;
          hasStreamMessage = true;
          setMessages((previous) => {
            if (shouldAppend) {
              return [...previous, { role: "bot", text: answer, sources: [] }];
            }
            return previous.map((message, index) => (
              index === previous.length - 1
                ? { ...message, text: answer }
                : message
            ));
          });
        },
      });
      if (controller.signal.aborted || requestId !== requestIdRef.current) return;
      historyRef.current = trimChatHistory([
        ...historyRef.current,
        { role: "assistant", content: response.answer },
      ]);
      setMessages((previous) => {
        if (!hasStreamMessage) {
          return [...previous, { role: "bot", text: response.answer, sources: response.sources }];
        }
        return previous.map((message, index) => (
          index === previous.length - 1
            ? { ...message, text: response.answer, sources: response.sources }
            : message
        ));
      });
    } catch (error) {
      if (controller.signal.aborted || requestId !== requestIdRef.current) return;
      console.error("Chat request failed", error);
      setMessages((previous) => (
        hasStreamMessage
          ? previous
          : [...previous, { role: "bot", text: chatErrorMessage(error) }]
      ));
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
    setMessages(initialChatMessages(displayName));
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
