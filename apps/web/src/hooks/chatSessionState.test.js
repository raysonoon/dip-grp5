import assert from "node:assert/strict";
import test from "node:test";

import { ApiNetworkError } from "../api/client.js";
import {
  MAX_CHAT_HISTORY_CONTENT_LENGTH,
  MAX_CHAT_QUESTION_LENGTH,
  normalizeChatQuestion,
} from "../api/chat.js";
import {
  INTERRUPTED_CHAT_MESSAGE,
  chatFailureMessage,
  completeChatHistory,
  removePendingRequestMessages,
} from "./chatSessionState.js";

test("a completed chat turn is committed as one bounded user-assistant pair", () => {
  const history = completeChatHistory(
    [],
    `  ${"q".repeat(MAX_CHAT_QUESTION_LENGTH + 20)}  `,
    `  ${"a".repeat(MAX_CHAT_HISTORY_CONTENT_LENGTH + 20)}  `,
  );

  assert.deepEqual(history.map((message) => message.role), ["user", "assistant"]);
  assert.equal(history[0].content.length, MAX_CHAT_QUESTION_LENGTH);
  assert.equal(history[1].content.length, MAX_CHAT_HISTORY_CONTENT_LENGTH);
});

test("an incomplete turn does not add a dangling user history entry", () => {
  const existing = [
    { role: "user", content: "Earlier question" },
    { role: "assistant", content: "Earlier answer" },
  ];

  assert.deepEqual(completeChatHistory(existing, "New question", ""), existing);
});

test("stopping a request removes its user message and partial assistant only", () => {
  const messages = [
    { role: "bot", text: "Greeting" },
    { role: "user", text: "Cancelled question", requestId: 7 },
    { role: "bot", text: "Partial answer", requestId: 7 },
    { role: "bot", text: "Unrelated", requestId: 6 },
  ];

  assert.deepEqual(removePendingRequestMessages(messages, 7), [
    { role: "bot", text: "Greeting" },
    { role: "bot", text: "Unrelated", requestId: 6 },
  ]);
});

test("a failure after a delta is explicit while an early failure keeps its normal message", () => {
  const error = new ApiNetworkError("offline");

  assert.equal(chatFailureMessage(error, true), INTERRUPTED_CHAT_MESSAGE);
  assert.match(chatFailureMessage(error, false), /connection|reach/i);
});

test("question normalization trims, bounds, and never leaves a split surrogate", () => {
  const normalized = normalizeChatQuestion(
    `  ${"x".repeat(MAX_CHAT_QUESTION_LENGTH - 1)}😀tail  `,
  );

  assert.equal(normalized.length, MAX_CHAT_QUESTION_LENGTH - 1);
  assert.doesNotMatch(normalized, /[\uD800-\uDBFF]$/u);
});
