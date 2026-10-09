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

export function trimChatHistory(history) {
  const kept = new Set();
  for (const role of ["user", "assistant"]) {
    const indexes = history
      .map((message, index) => (message.role === role ? index : -1))
      .filter((index) => index >= 0);
    indexes.slice(-MAX_CHAT_MESSAGES_PER_ROLE).forEach((index) => kept.add(index));
  }
  return history.filter((_message, index) => kept.has(index));
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

export async function streamChat(
  /** @type {string} */
  question,
  /** @type {{ history?: Array<{ role: "user" | "assistant", content: string }>, sessionId?: string, signal?: AbortSignal, onDelta?: (delta: string, answer: string) => void }} */
  { history = [], sessionId, signal, onDelta = () => {} } = {},
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
      question,
      history: trimChatHistory(history),
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
    }
  }

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    buffer = buffer.replaceAll("\r\n", "\n");
    let boundary = buffer.indexOf("\n\n");
    while (boundary >= 0) {
      await handleBlock(buffer.slice(0, boundary));
      buffer = buffer.slice(boundary + 2);
      boundary = buffer.indexOf("\n\n");
    }
    if (done) break;
  }
  if (buffer.trim()) await handleBlock(buffer.trim());
  if (sources === null) {
    throw new ChatResponseError("Chat API stream ended before sources arrived");
  }
  return { answer, sources };
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
