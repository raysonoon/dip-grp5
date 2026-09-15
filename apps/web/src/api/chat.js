import {
  ApiError,
  ApiNetworkError,
  ApiResponseError,
  ApiTimeoutError,
  apiClient,
} from "./client.js";

const CHAT_TIMEOUT_MS = 30_000;

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

function parseSource(value) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new ChatResponseError("Invalid source in chat API response");
  }
  if (typeof value.source_type !== "string" || typeof value.excerpt !== "string") {
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
    excerpt: value.excerpt,
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

export async function askChat(question) {
  const payload = await apiClient.post(
    "/chat",
    { question },
    { auth: false, timeoutMs: CHAT_TIMEOUT_MS },
  );
  return parseChatResponse(payload);
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
