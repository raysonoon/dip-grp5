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
  trimChatHistory,
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
      permalink: null,
      location: null,
      unit_code: null,
      category: null,
      price_range: null,
      opening_hours: null,
      rating: null,
      count: null,
    },
  ],
};

const SQL_CHAT_RESPONSE = {
  answer: "Here are some halal options.",
  sources: [
    {
      source_type: "vendor",
      source_id: "6",
      vendor_id: 6,
      vendor_name: "Ananda's TAJ Restaurant",
      excerpt: null,
      permalink: null,
      location: "60 Nanyang Cres",
      unit_code: "BJH-01-02",
      category: "Indian restaurant",
      price_range: "$10-20",
      opening_hours: "Daily: 11.30am to 10.30pm",
      rating: 3.6,
      count: null,
    },
    {
      source_type: "count",
      source_id: null,
      vendor_id: null,
      vendor_name: null,
      excerpt: null,
      permalink: null,
      location: null,
      unit_code: null,
      category: null,
      price_range: null,
      opening_hours: null,
      rating: null,
      count: 5,
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
    assert.equal(options.body, JSON.stringify({
      session_id: "session-a",
      question: "What should I eat?",
      history: [
        { role: "user", content: "I want noodles." },
        { role: "assistant", content: "Try Demo Vendor 1." },
      ],
    }));
    return jsonResponse(CHAT_RESPONSE);
  };

  const response = await askChat("What should I eat?", {
    sessionId: "session-a",
    history: [
      { role: "user", content: "I want noodles." },
      { role: "assistant", content: "Try Demo Vendor 1." },
    ],
  });

  assert.equal(response.answer, CHAT_RESPONSE.answer);
  assert.deepEqual(response.sources, CHAT_RESPONSE.sources);
});

test("askChat parses SQL search type vendor and count sources", async (context) => {
  const originalFetch = globalThis.fetch;
  context.after(() => {
    globalThis.fetch = originalFetch;
  });
  globalThis.fetch = async () => jsonResponse(SQL_CHAT_RESPONSE);

  const response = await askChat("Where can I find halal food?", {
    sessionId: "session-a",
  });

  assert.deepEqual(response.sources, SQL_CHAT_RESPONSE.sources);
  assert.equal(response.sources[0].source_type, "vendor");
  assert.equal(response.sources[0].vendor_name, "Ananda's TAJ Restaurant");
  assert.equal(response.sources[0].rating, 3.6);
  assert.equal(response.sources[1].source_type, "count");
  assert.equal(response.sources[1].count, 5);
});

test("askChat rejects a source with an invalid excerpt type", async (context) => {
  const originalFetch = globalThis.fetch;
  context.after(() => {
    globalThis.fetch = originalFetch;
  });
  globalThis.fetch = async () =>
    jsonResponse({
      answer: "x",
      sources: [{ source_type: "vendor", excerpt: 123 }],
    });

  await assert.rejects(
    askChat("Question", { sessionId: "session-a" }),
    ChatResponseError,
  );
});

test("askChat rejects a malformed ChatResponse", async (context) => {
  const originalFetch = globalThis.fetch;
  context.after(() => {
    globalThis.fetch = originalFetch;
  });
  globalThis.fetch = async () => jsonResponse({ answer: 123, sources: [] });

  await assert.rejects(
    askChat("Question", { sessionId: "session-a" }),
    ChatResponseError,
  );
});

test("chat history keeps the newest five messages for each role", () => {
  const history = Array.from({ length: 7 }, (_, index) => [
    { role: "user", content: `user-${index}` },
    { role: "assistant", content: `assistant-${index}` },
  ]).flat();

  assert.deepEqual(
    trimChatHistory(history),
    Array.from({ length: 5 }, (_, offset) => {
      const index = offset + 2;
      return [
        { role: "user", content: `user-${index}` },
        { role: "assistant", content: `assistant-${index}` },
      ];
    }).flat(),
  );
});

test("askChat forwards a caller abort signal", async (context) => {
  const originalFetch = globalThis.fetch;
  context.after(() => {
    globalThis.fetch = originalFetch;
  });
  globalThis.fetch = (_path, options) => new Promise((_resolve, reject) => {
    options.signal.addEventListener("abort", () => {
      reject(new DOMException("aborted", "AbortError"));
    });
  });
  const controller = new AbortController();
  const request = askChat("Slow question", {
    sessionId: "session-a",
    signal: controller.signal,
  });

  controller.abort();

  await assert.rejects(request, (error) => error.name === "AbortError");
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

test("the API timeout remains active while the response body is read", async (context) => {
  const originalFetch = globalThis.fetch;
  context.after(() => {
    globalThis.fetch = originalFetch;
  });

  globalThis.fetch = async (_path, options) => ({
    status: 200,
    ok: true,
    headers: new Headers({ "Content-Type": "application/json" }),
    json: () => new Promise((_resolve, reject) => {
      options.signal.addEventListener("abort", () => {
        reject(new DOMException("aborted", "AbortError"));
      });
    }),
  });

  await assert.rejects(
    apiClient.get("/slow-body", { auth: false, timeoutMs: 1 }),
    ApiTimeoutError,
  );
});

test("chat errors map to non-blocking retry messages", () => {
  assert.match(chatErrorMessage(new ApiNetworkError("offline")), /connection|reach/i);
  assert.match(chatErrorMessage(new ApiTimeoutError(1)), /too long/i);
  assert.match(chatErrorMessage(new ApiError("failed", 500, null)), /try again/i);
  assert.match(chatErrorMessage(new ChatResponseError("bad response")), /unexpected/i);
});
