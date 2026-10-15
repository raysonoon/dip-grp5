import {
  chatErrorMessage,
  normalizeChatHistoryContent,
  normalizeChatQuestion,
  trimChatHistory,
} from "../api/chat.js";

export const INTERRUPTED_CHAT_MESSAGE =
  "Foodie's response was interrupted before it finished. The partial answer above was not saved. Please try again.";

/**
 * Commit a complete turn atomically so failed or cancelled questions never
 * become dangling user history entries.
 *
 * @param {Array<{ role: "user" | "assistant", content: string }>} history
 * @param {string} question
 * @param {string} answer
 */
export function completeChatHistory(history, question, answer) {
  const normalizedQuestion = normalizeChatQuestion(question);
  const normalizedAnswer = normalizeChatHistoryContent(answer);
  if (!normalizedQuestion || !normalizedAnswer) return trimChatHistory(history);

  return trimChatHistory([
    ...history,
    { role: "user", content: normalizedQuestion },
    { role: "assistant", content: normalizedAnswer },
  ]);
}

/**
 * @template {{ requestId?: number }} T
 * @param {T[]} messages
 * @param {number} requestId
 * @returns {T[]}
 */
export function removePendingRequestMessages(messages, requestId) {
  return messages.filter((message) => message.requestId !== requestId);
}

export function chatFailureMessage(error, hasPartialAnswer) {
  return hasPartialAnswer ? INTERRUPTED_CHAT_MESSAGE : chatErrorMessage(error);
}
