import {
  ApiError,
  ApiNetworkError,
  ApiResponseError,
  ApiTimeoutError,
  apiUrl,
} from "./client.js";
import { getAccessToken } from "../lib/auth.js";

export class ChatResponseError extends Error {
  constructor(message) {
    super(message);
    this.name = "ChatResponseError";
  }
}

function nullableString(value, label) {
  if (value !== null && typeof value !== "string") {
    throw new ChatResponseError(`Invalid ${label} in chat API response`);
  }
  return value;
}

function nullableNumber(value, label) {
  if (value !== null && typeof value !== "number") {
    throw new ChatResponseError(`Invalid ${label} in chat API response`);
  }
  return value;
}

function parseSource(value) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new ChatResponseError("Invalid source in chat API response");
  }
  if (typeof value.source_type !== "string") {
    throw new ChatResponseError("Invalid source in chat API response");
  }
  if (value.vendor_id !== null && !Number.isInteger(value.vendor_id)) {
    throw new ChatResponseError("Invalid source vendor_id in chat API response");
  }
  return {
    source_type: value.source_type,
    source_id: nullableString(value.source_id, "source_id"),
    vendor_id: value.vendor_id,
    vendor_name: nullableString(value.vendor_name, "vendor_name"),
    excerpt: nullableString(value.excerpt, "excerpt"),
    permalink: nullableString(value.permalink, "permalink"),
    maps_url: nullableString(value.maps_url ?? null, "maps_url"),
    location: nullableString(value.location, "location"),
    unit_code: nullableString(value.unit_code, "unit_code"),
    category: nullableString(value.category, "category"),
    price_range: nullableString(value.price_range, "price_range"),
    opening_hours: nullableString(value.opening_hours, "opening_hours"),
    rating: nullableNumber(value.rating, "rating"),
    count: nullableNumber(value.count, "count"),
  };
}

export function parseChatResponse(value) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new ChatResponseError("Invalid chat API response");
  }
  if (typeof value.answer !== "string" || !Array.isArray(value.sources)) {
    throw new ChatResponseError("Invalid chat API response");
  }
  return {
    answer: value.answer,
    sources: value.sources.map(parseSource),
  };
}

export const MAX_CHAT_MESSAGES_PER_ROLE = 5;
export const MAX_CHAT_QUESTION_LENGTH = 2_000;
export const MAX_CHAT_HISTORY_CONTENT_LENGTH = 4_000;

function boundedText(value, maxLength) {
  const trimmed = value.trim();
  let clipped = trimmed.slice(0, maxLength);
  const finalCodeUnit = clipped.charCodeAt(clipped.length - 1);
  if (finalCodeUnit >= 0xD800 && finalCodeUnit <= 0xDBFF) {
    clipped = clipped.slice(0, -1);
  }
  return clipped;
}

export function normalizeChatQuestion(value) {
  return boundedText(value, MAX_CHAT_QUESTION_LENGTH);
}

export function normalizeChatHistoryContent(value) {
  return boundedText(value, MAX_CHAT_HISTORY_CONTENT_LENGTH);
}

export function trimChatHistory(history) {
  const kept = new Set();
  for (const role of ["user", "assistant"]) {
    const indexes = history
      .map((message, index) => (message.role === role ? index : -1))
      .filter((index) => index >= 0);
    indexes.slice(-MAX_CHAT_MESSAGES_PER_ROLE).forEach((index) => kept.add(index));
  }
  return history
    .filter((_message, index) => kept.has(index))
    .map((message) => ({
      ...message,
      content: normalizeChatHistoryContent(message.content),
    }))
    .filter((message) => message.content);
}

function parseEventBlock(block) {
  let event = "message";
  const data = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
  }
  return { event, data: data.join("\n") };
}

function parseSources(value) {
  if (!Array.isArray(value)) {
    throw new ChatResponseError("Invalid sources event in chat API response");
  }
  return value.map(parseSource);
}

export const CHAT_IDLE_TIMEOUT_MS = 30_000;
export const CHAT_REQUEST_TIMEOUT_MS = 30_000;

/** @returns {Promise<{ answer: string, sources: ReturnType<typeof parseSource>[] }>} */
export async function streamChat(
  question,
  /** @type {{ history?: Array<{ role: "user" | "assistant", content: string }>, sessionId?: string, foodPick?: string, action?: "recommend_pick", signal?: AbortSignal, onDelta?: (delta: string, answer: string) => void, idleTimeoutMs?: number, timeoutMs?: number }} */
  {
    signal,
    idleTimeoutMs = CHAT_IDLE_TIMEOUT_MS,
    timeoutMs = CHAT_REQUEST_TIMEOUT_MS,
    ...options
  } = {},
) {
  const controller = new AbortController();
  let idleTimer;
  const abortFromCaller = () => controller.abort(
    signal.reason ?? new DOMException("The operation was aborted", "AbortError"),
  );
  /** @type {Promise<never>} */
  const aborted = new Promise((_resolve, reject) => {
    controller.signal.addEventListener("abort", () => reject(controller.signal.reason), {
      once: true,
    });
  });
  const resetIdleTimeout = () => {
    clearTimeout(idleTimer);
    idleTimer = setTimeout(() => controller.abort(new ApiTimeoutError(idleTimeoutMs)), idleTimeoutMs);
  };
  const totalTimer = setTimeout(() => controller.abort(new ApiTimeoutError(timeoutMs)), timeoutMs);
  resetIdleTimeout();
  if (signal?.aborted) abortFromCaller();
  else signal?.addEventListener("abort", abortFromCaller, { once: true });

  try {
    // Race the whole operation so even a stalled auth lookup or response body
    // cannot leave the chat waiting after the deadline or a user cancellation.
    return await Promise.race([
      readChatStream(question, {
        ...options,
        signal: controller.signal,
        onProgress: resetIdleTimeout,
      }),
      aborted,
    ]);
  } catch (error) {
    if (controller.signal.aborted) throw controller.signal.reason;
    if (error instanceof TypeError) throw new ApiNetworkError("Chat connection interrupted", error);
    throw error;
  } finally {
    clearTimeout(idleTimer);
    clearTimeout(totalTimer);
    signal?.removeEventListener("abort", abortFromCaller);
    controller.abort();
  }
}

async function readChatStream(
  /** @type {string} */
  question,
  { history = [], sessionId, foodPick, action, signal, onDelta = () => {}, onProgress },
) {
  const accessToken = await getAccessToken();
  if (signal?.aborted) {
    throw signal.reason ?? new DOMException("The operation was aborted", "AbortError");
  }

  let response;
  try {
    const headers = { "Content-Type": "application/json" };
    if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
    response = await fetch(apiUrl("/chat/stream"), {
      method: "POST",
      headers,
      body: JSON.stringify({
        session_id: sessionId,
        ...(action === "recommend_pick" ? { action } : { question }),
        history: trimChatHistory(history),
        ...(foodPick ? { food_pick: foodPick } : {}),
      }),
      signal,
    });
  } catch (error) {
    if (signal?.aborted) throw error;
    throw new ApiNetworkError("Could not connect to the API", error);
  }

  if (!response.ok) {
    let payload = null;
    try {
      payload = await response.json();
    } catch {
      // The status code is enough when an upstream server returns non-JSON.
    }
    const message = typeof payload?.detail === "string"
      ? payload.detail
      : `Request failed with status ${response.status}`;
    throw new ApiError(message, response.status, payload);
  }
  if (!response.headers.get("content-type")?.includes("text/event-stream")) {
    throw new ChatResponseError("Chat API did not return an event stream");
  }
  if (!response.body) {
    throw new ChatResponseError("Chat API returned an empty event stream");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let answer = "";
  let sources = null;

  async function handleBlock(block) {
    const parsed = parseEventBlock(block);
    if (!parsed.data) return;
    let data;
    try {
      data = JSON.parse(parsed.data);
    } catch (error) {
      throw new ChatResponseError(`Invalid ${parsed.event} event JSON`, { cause: error });
    }
    if (parsed.event === "delta") {
      if (typeof data !== "string") {
        throw new ChatResponseError("Invalid delta event in chat API response");
      }
      answer += data;
      await onDelta(data, answer);
    } else if (parsed.event === "sources") {
      sources = parseSources(data);
    } else if (parsed.event === "error") {
      // Only expose a stable public message, never server diagnostics.
      throw new ApiError("Foodie is temporarily unavailable", 503, null);
    }
  }

  const cancelReader = () => { void reader.cancel().catch(() => {}); };
  signal.addEventListener("abort", cancelReader, { once: true });
  try {
    while (true) {
      signal.throwIfAborted();
      const { done, value } = await reader.read();
      signal.throwIfAborted();
      if (value?.length) onProgress();
      buffer += decoder.decode(value, { stream: !done });
      buffer = buffer.replaceAll("\r\n", "\n");
      let boundary = buffer.indexOf("\n\n");
      while (boundary >= 0) {
        await handleBlock(buffer.slice(0, boundary));
        buffer = buffer.slice(boundary + 2);
        if (sources !== null) return { answer, sources };
        boundary = buffer.indexOf("\n\n");
      }
      if (done) break;
    }
    if (buffer.trim()) await handleBlock(buffer.trim());
    if (sources === null) {
      throw new ChatResponseError("Chat API stream ended before sources arrived");
    }
    return { answer, sources };
  } finally {
    signal.removeEventListener("abort", cancelReader);
    cancelReader();
    reader.releaseLock();
  }
}

export function chatErrorMessage(error) {
  if (error instanceof ApiTimeoutError) {
    return "Foodie took too long to respond. Please try again.";
  }
  if (error instanceof ApiNetworkError) {
    return "I couldn't reach Foodie right now. Check your connection and try again.";
  }
  if (error instanceof ApiResponseError || error instanceof ChatResponseError) {
    return "Foodie returned an unexpected response. Please try again.";
  }
  if (error instanceof ApiError) {
    return "Foodie couldn't answer that right now. Please try again.";
  }
  return "Something went wrong while asking Foodie. Please try again.";
}
