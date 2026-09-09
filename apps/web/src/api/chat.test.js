import assert from "node:assert/strict";
import test from "node:test";

import {
  ApiError,
  ApiNetworkError,
  ApiResponseError,
  ApiTimeoutError,
  apiClient,
} from "./client.js";
import {
  ChatResponseError,
  askChat,
  chatErrorMessage,
} from "./chat.js";

const CHAT_RESPONSE = {
  answer: "Try Demo Vendor 1.",
  sources: [
    {
      source_type: "internal_review",
      source_id: "1",
      vendor_id: 1,
      vendor_name: "Demo Vendor 1",
      excerpt: "Great chicken rice.",
    },
  ],
};

function jsonResponse(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

test("askChat posts the ChatRequest publicly and parses ChatResponse", async (context) => {
  const originalFetch = globalThis.fetch;
  context.after(() => {
    globalThis.fetch = originalFetch;
  });
  globalThis.fetch = async (path, options) => {
    assert.equal(path, "/chat");
    assert.equal(options.method, "POST");
    assert.equal(options.headers["X-Dev-User-Id"], undefined);
    assert.equal(options.headers["Content-Type"], "application/json");
    assert.equal(options.body, JSON.stringify({ question: "What should I eat?" }));
    return jsonResponse(CHAT_RESPONSE);
  };

  const response = await askChat("What should I eat?");

  assert.equal(response.answer, CHAT_RESPONSE.answer);
  assert.deepEqual(response.sources, CHAT_RESPONSE.sources);
});

test("askChat rejects a malformed ChatResponse", async (context) => {
  const originalFetch = globalThis.fetch;
  context.after(() => {
    globalThis.fetch = originalFetch;
  });
  globalThis.fetch = async () => jsonResponse({ answer: 123, sources: [] });

  await assert.rejects(askChat("Question"), ChatResponseError);
});

test("the API client distinguishes network, HTTP, malformed-body, and timeout errors", async (context) => {
  const originalFetch = globalThis.fetch;
  context.after(() => {
    globalThis.fetch = originalFetch;
  });

  globalThis.fetch = async () => {
    throw new TypeError("connection refused");
  };
  await assert.rejects(apiClient.get("/network", { auth: false }), ApiNetworkError);

  globalThis.fetch = async () => jsonResponse({ detail: "backend failed" }, 503);
  await assert.rejects(apiClient.get("/http", { auth: false }), ApiError);

  globalThis.fetch = async () => new Response("not json", {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
  await assert.rejects(apiClient.get("/malformed", { auth: false }), ApiResponseError);

  globalThis.fetch = (_path, options) => new Promise((_resolve, reject) => {
    options.signal.addEventListener("abort", () => {
      reject(new DOMException("aborted", "AbortError"));
    });
  });
  await assert.rejects(
    apiClient.get("/timeout", { auth: false, timeoutMs: 1 }),
    ApiTimeoutError,
  );
});

test("chat errors map to non-blocking retry messages", () => {
  assert.match(chatErrorMessage(new ApiNetworkError("offline")), /connection|reach/i);
  assert.match(chatErrorMessage(new ApiTimeoutError(1)), /too long/i);
  assert.match(chatErrorMessage(new ApiError("failed", 500, null)), /try again/i);
  assert.match(chatErrorMessage(new ChatResponseError("bad response")), /unexpected/i);
});
