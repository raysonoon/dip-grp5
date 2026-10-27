import { useEffect, useReducer, useRef, useState } from "react";

import { normalizeChatQuestion, streamChat, trimChatHistory } from "../api/chat";
import { useAuth } from "../contexts/AuthContext";
import { createWheelSession, wheelSessionReducer } from "../lib/vendorWheel.js";
import { pickerRecommendationSources } from "../lib/foodPicker.js";
import {
  chatFailureMessage,
  completeChatHistory,
  removePendingRequestMessages,
} from "./chatSessionState.js";

const ANONYMOUS_CHAT_GREETING = "Hey! Time to makan 🍜 What are you craving? Not sure? Try the food picker!";

type ChatHistoryMessage = {
  role: "user" | "assistant";
  content: string;
};

export type ChatUiMessage = {
  role: "user" | "bot";
  text: string;
  sources?: unknown[];
  requestId?: number;
};

function createChatSessionId() {
  return globalThis.crypto?.randomUUID?.()
    ?? `chat-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function initialChatMessages(displayName: string | null): ChatUiMessage[] {
  const greeting = displayName
    ? `Hey ${displayName}! Time to makan 🍜 What are you craving? Not sure? Try the food picker!`
    : ANONYMOUS_CHAT_GREETING;
  return [{ role: "bot", text: greeting }];
}

export function useChatSession({ foodPick }: { foodPick?: string } = {}) {
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
  const [wheelSession, dispatchWheel] = useReducer(wheelSessionReducer, undefined, createWheelSession);
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

  async function sendMessage(text: string, { fromPicker = false }: { fromPicker?: boolean } = {}) {
    const question = fromPicker ? "" : normalizeChatQuestion(text);
    if ((!question && !fromPicker) || (fromPicker && !foodPick) || requestPendingRef.current) return;

    const controller = new AbortController();
    const requestId = ++requestIdRef.current;
    const historyForRequest = historyRef.current;
    activeControllerRef.current = controller;
    requestPendingRef.current = true;
    if (!fromPicker) {
      setMessages((previous) => [
        ...previous,
        { role: "user", text: question, requestId },
      ]);
      setInput("");
    }
    setIsGenerating(true);

    let hasStreamMessage = false;
    try {
      const response = await streamChat(question, {
        history: historyForRequest,
        sessionId: sessionIdRef.current,
        foodPick,
        action: fromPicker ? "recommend_pick" : undefined,
        signal: controller.signal,
        onDelta: (_delta: string, answer: string) => {
          if (controller.signal.aborted || requestId !== requestIdRef.current) return;
          const shouldAppend = !hasStreamMessage;
          hasStreamMessage = true;
          setMessages((previous) => {
            if (shouldAppend) {
              return [
                ...previous,
                { role: "bot", text: answer, sources: [], requestId },
              ];
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
      dispatchWheel({ type: "sources", sources: fromPicker
        ? pickerRecommendationSources(response.answer, response.sources)
        : response.sources });
      historyRef.current = fromPicker
        ? trimChatHistory([...historyForRequest, { role: "assistant", content: response.answer }])
        : completeChatHistory(historyForRequest, question, response.answer);
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
      setMessages((previous) => [
        ...previous,
        {
          role: "bot",
          text: chatFailureMessage(error, hasStreamMessage),
          requestId,
        },
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
    const stoppedRequestId = requestIdRef.current;
    requestIdRef.current += 1;
    activeControllerRef.current?.abort();
    activeControllerRef.current = null;
    requestPendingRef.current = false;
    setMessages((previous) => (
      removePendingRequestMessages(previous, stoppedRequestId)
    ));
    setIsGenerating(false);
  }

  function startNewSession() {
    stopResponse();
    historyRef.current = [];
    sessionIdRef.current = createChatSessionId();
    dispatchWheel({ type: "reset" });
    setMessages(initialChatMessages(displayName));
    setInput("");
  }

  return {
    input,
    isGenerating,
    messages,
    sendMessage,
    recommendFoodPick: () => sendMessage("", { fromPicker: true }),
    setInput,
    startNewSession,
    stopResponse,
    wheelVendors: wheelSession.vendors,
    removeWheelVendor: (vendorId: number) => dispatchWheel({ type: "remove", vendorId }),
  };
}
