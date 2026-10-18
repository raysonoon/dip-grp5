import { apiUrl } from "./client.js";
import { getAccessToken } from "../lib/auth.js";

/**
 * Load one page of the signed-in user's reviews, most recent first.
 * Resolves to `{ items, total, limit, offset }`.
 */
export async function fetchMyReviews({ limit = 10, offset = 0 } = {}) {
  const token = await getAccessToken();

  if (!token) {
    throw new Error("You must be signed in");
  }

  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  const response = await fetch(apiUrl(`/auth/me/reviews?${params}`), {
    headers: { Authorization: `Bearer ${token}` },
  });

  if (!response.ok) {
    throw new Error(`Reviews request failed (${response.status})`);
  }

  return response.json();
}
