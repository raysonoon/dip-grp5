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
  chatErrorMessage,
  parseChatResponse,
  streamChat,
  trimChatHistory,
} from "./chat.js";
import { supabase } from "../lib/supabase.js";

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
      maps_url: null,
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
      maps_url: null,
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
      maps_url: null,
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

function streamResponse(chunks, status = 200) {
  const encoder = new TextEncoder();
  return new Response(new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  }), {
    status,
    headers: { "Content-Type": "text/event-stream" },
  });
}

function configureSession(context, accessToken = "test-access-token") {
  const originalDescriptor = Object.getOwnPropertyDescriptor(
    supabase.auth,
    "getSession",
  );
  Object.defineProperty(supabase.auth, "getSession", {
    configurable: true,
    value: async () => ({
    data: { session: { access_token: accessToken } },
    error: null,
    }),
  });
  context.after(() => {
    if (originalDescriptor) {
      Object.defineProperty(supabase.auth, "getSession", originalDescriptor);
    } else {
      delete supabase.auth.getSession;
    }
  });
}

test("the latest picker result is sent as context without changing the question or persisting", async (context) => {
  configureSession(context, null);
  const originalFetch = globalThis.fetch;
  context.after(() => { globalThis.fetch = originalFetch; });
  const requests = [];
  globalThis.fetch = async (_path, options) => {
    requests.push(JSON.parse(options.body));
    return streamResponse(['event: delta\ndata: "A food idea."\n\nevent: sources\ndata: []\n\n']);
  };
  await streamChat("What did I roll?", { foodPick: "Roti prata" });
  await streamChat("What did I roll?");
  await streamChat("", { foodPick: "Poke bowls", action: "recommend_pick" });
  assert.equal(requests[0].question, "What did I roll?");
  assert.equal(requests[0].food_pick, "Roti prata");
  assert.deepEqual(requests[0].history, []);
  assert.equal("food_pick" in requests[1], false);
  assert.equal(requests[2].action, "recommend_pick");
  assert.equal(requests[2].food_pick, "Poke bowls");
  assert.equal("question" in requests[2], false);
});

test("streamChat sends auth and incrementally parses fragmented SSE events", async (context) => {
  configureSession(context, "42");
  const originalFetch = globalThis.fetch;
  context.after(() => {
    globalThis.fetch = originalFetch;
  });
  globalThis.fetch = async (path, options) => {
    assert.equal(path, "/chat/stream");
    assert.equal(options.method, "POST");
    assert.equal(options.headers.Authorization, "Bearer 42");
    assert.equal(options.headers["Content-Type"], "application/json");
    assert.equal(options.body, JSON.stringify({
      session_id: "session-a",
      question: "What should I eat?",
      history: [
        { role: "user", content: "I want noodles." },
        { role: "assistant", content: "Try Demo Vendor 1." },
      ],
    }));
    return streamResponse([
      'event: delta\ndata: "Try "\n\nevent: del',
      'ta\ndata: "Demo Vendor 1."\n\n',
      `event: sources\ndata: ${JSON.stringify(CHAT_RESPONSE.sources)}\n`,
      "\n",
    ]);
  };

  const updates = [];
  const response = await streamChat("What should I eat?", {
    sessionId: "session-a",
    history: [
      { role: "user", content: "I want noodles." },
      { role: "assistant", content: "Try Demo Vendor 1." },
    ],
    onDelta: (_delta, answer) => updates.push(answer),
  });

  assert.equal(response.answer, CHAT_RESPONSE.answer);
  assert.deepEqual(response.sources, CHAT_RESPONSE.sources);
  assert.deepEqual(updates, ["Try ", CHAT_RESPONSE.answer]);
});

test("streamChat allows anonymous requests without an Authorization header", async (context) => {
  configureSession(context, null);
  const originalFetch = globalThis.fetch;
  context.after(() => {
    globalThis.fetch = originalFetch;
  });
  globalThis.fetch = async (_path, options) => {
    assert.equal(options.headers.Authorization, undefined);
    return streamResponse([
      'event: delta\ndata: "Try it. d"\n\n',
      `event: sources\ndata: ${JSON.stringify([])}\n\n`,
    ]);
  };

  const response = await streamChat("What should I eat?");

  assert.equal(response.answer, "Try it. d");
  assert.deepEqual(response.sources, []);
});

test("parseChatResponse accepts SQL vendor and count sources", () => {
  const response = parseChatResponse(SQL_CHAT_RESPONSE);

  assert.deepEqual(response.sources, SQL_CHAT_RESPONSE.sources);
  assert.equal(response.sources[0].source_type, "vendor");
  assert.equal(response.sources[0].vendor_name, "Ananda's TAJ Restaurant");
  assert.equal(response.sources[0].rating, 3.6);
  assert.equal(response.sources[1].source_type, "count");
  assert.equal(response.sources[1].count, 5);
});

test("parseChatResponse rejects a source with an invalid excerpt type", () => {
  assert.throws(
    () => parseChatResponse({
      answer: "x",
      sources: [{ source_type: "vendor", excerpt: 123 }],
    }),
    ChatResponseError,
  );
});

test("parseChatResponse rejects a malformed ChatResponse", () => {
  assert.throws(
    () => parseChatResponse({ answer: 123, sources: [] }),
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

test("streamChat preserves caller cancellation", async (context) => {
  configureSession(context, "42");
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
  const request = streamChat("Slow question", {
    sessionId: "session-a",
    signal: controller.signal,
  });

  controller.abort();

  await assert.rejects(request, (error) => error.name === "AbortError");
});

test("streamChat rejects a partial answer when the final sources event is missing", async (context) => {
  configureSession(context, null);
  const originalFetch = globalThis.fetch;
  context.after(() => {
    globalThis.fetch = originalFetch;
  });
  globalThis.fetch = async () => streamResponse([
    'event: delta\ndata: "Partial answer"\n\n',
  ]);

  const updates = [];
  await assert.rejects(
    streamChat("Interrupted question", {
      onDelta: (_delta, answer) => updates.push(answer),
    }),
    (error) => (
      error instanceof ChatResponseError
      && /before sources arrived/.test(error.message)
    ),
  );
  assert.deepEqual(updates, ["Partial answer"]);
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

function replaceFetch(context, fetch) {
  context.mock.method(globalThis, "fetch", fetch);
}

test("chat times out while waiting for headers and aborts the request", async (context) => {
  configureSession(context, null);
  let signal;
  replaceFetch(context, (_path, options) => {
    signal = options.signal;
    return new Promise(() => {});
  });
  await assert.rejects(streamChat("Hello", { idleTimeoutMs: 10 }), ApiTimeoutError);
  assert.equal(signal.aborted, true);
});

test("chat deadline includes a stalled authentication lookup", async (context) => {
  configureSession(context, null);
  Object.defineProperty(supabase.auth, "getSession", {
    configurable: true,
    value: () => new Promise(() => {}),
  });
  replaceFetch(context, () => { throw new Error("fetch must not run"); });
  await assert.rejects(streamChat("Hello", { idleTimeoutMs: 10 }), ApiTimeoutError);
});

test("chat times out on a silent stream and on a stream that stalls after a delta", async (context) => {
  configureSession(context, null);
  for (const partial of [false, true]) {
    let cancelled = false;
    const updates = [];
    replaceFetch(context, async () => new Response(new ReadableStream({
      start(controller) {
        if (partial) controller.enqueue(new TextEncoder().encode('event: delta\ndata: "Partial"\n\n'));
      },
      cancel() { cancelled = true; },
    }), { headers: { "Content-Type": "text/event-stream" } }));
    await assert.rejects(streamChat("Hello", {
      idleTimeoutMs: 10,
      onDelta: (_delta, answer) => updates.push(answer),
    }), ApiTimeoutError);
    assert.equal(cancelled, true);
    assert.deepEqual(updates, partial ? ["Partial"] : []);
  }
});

test("chat times out even while reading an HTTP error body", async (context) => {
  configureSession(context, null);
  replaceFetch(context, async () => ({
    ok: false, status: 503, json: () => new Promise(() => {}),
  }));
  await assert.rejects(streamChat("Hello", { idleTimeoutMs: 10 }), ApiTimeoutError);
});

test("chat completes on final sources without waiting for the connection to close", async (context) => {
  configureSession(context, null);
  let cancelled = false;
  replaceFetch(context, async () => new Response(new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(
        'event: delta\ndata: "Complete answer"\n\nevent: sources\ndata: []\n\n',
      ));
    },
    cancel() { cancelled = true; },
  }), { headers: { "Content-Type": "text/event-stream" } }));
  assert.deepEqual(await streamChat("Hello", { idleTimeoutMs: 100 }), {
    answer: "Complete answer", sources: [],
  });
  assert.equal(cancelled, true);
});

test("server error events reject partial answers and a subsequent request succeeds", async (context) => {
  configureSession(context, null);
  for (const partial of [false, true]) {
    replaceFetch(context, async () => streamResponse([
      ...(partial ? ['event: delta\ndata: "Partial"\n\n'] : []),
      'event: error\ndata: {"code":"chat_unavailable","message":"private diagnostics"}\n\n',
    ]));
    await assert.rejects(streamChat("Hello"), (error) => (
      error instanceof ApiError && error.status === 503
      && !error.message.includes("private diagnostics")
    ));
  }
  replaceFetch(context, async () => streamResponse([
    'event: delta\ndata: "Recovered"\n\nevent: sources\ndata: []\n\n',
  ]));
  assert.equal((await streamChat("Try again")).answer, "Recovered");
});

test("chat handles HTTP 503 without exposing server details in its UI message", async (context) => {
  configureSession(context, null);
  replaceFetch(context, async () => jsonResponse({ detail: "private diagnostic" }, 503));
  await assert.rejects(streamChat("Hello"), (error) => (
    error instanceof ApiError && error.status === 503
    && /try again/i.test(chatErrorMessage(error))
    && !chatErrorMessage(error).includes("private diagnostic")
  ));
});

test("stopping a partial stream cancels its reader and preserves AbortError", async (context) => {
  configureSession(context, null);
  let cancelled = false;
  const controller = new AbortController();
  replaceFetch(context, async () => new Response(new ReadableStream({
    start(stream) {
      stream.enqueue(new TextEncoder().encode('event: delta\ndata: "Partial"\n\n'));
    },
    cancel() { cancelled = true; },
  }), { headers: { "Content-Type": "text/event-stream" } }));
  await assert.rejects(streamChat("Hello", {
    signal: controller.signal,
    onDelta: () => controller.abort(),
  }), (error) => error.name === "AbortError");
  assert.equal(cancelled, true);
});

test("active streams reset idle timeout but cannot run beyond the total deadline", async (context) => {
  configureSession(context, null);
  let timer;
  let cancelled = false;
  context.after(() => clearInterval(timer));
  replaceFetch(context, async () => new Response(new ReadableStream({
    start(controller) {
      timer = setInterval(() => controller.enqueue(new TextEncoder().encode(
        'event: delta\ndata: "word "\n\n',
      )), 5);
    },
    cancel() { clearInterval(timer); cancelled = true; },
  }), { headers: { "Content-Type": "text/event-stream" } }));
  let chunks = 0;
  await assert.rejects(streamChat("Hello", {
    idleTimeoutMs: 30,
    timeoutMs: 80,
    onDelta: () => { chunks += 1; },
  }), (error) => error instanceof ApiTimeoutError && error.timeoutMs === 80);
  assert.ok(chunks > 1);
  assert.equal(cancelled, true);
});
