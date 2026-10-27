import { apiUrl } from "./client.js";
import { getAccessToken } from "../lib/auth.js";

/**
 * Load one page of the signed-in user's reviews, most recent first.
 * Pass `vendorId` to look up only the user's review of that vendor.
 * Resolves to `{ items, total, limit, offset }`.
 */
export async function fetchMyReviews({ vendorId, limit = 10, offset = 0, signal } = {}) {
  const token = await getAccessToken();

  if (!token) {
    throw new Error("You must be signed in");
  }

  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  if (vendorId != null) params.set("vendor_id", String(vendorId));
  const response = await fetch(apiUrl(`/auth/me/reviews?${params}`), {
    headers: { Authorization: `Bearer ${token}` },
    signal,
  });

  if (!response.ok) {
    throw new Error(`Reviews request failed (${response.status})`);
  }

  return response.json();
}
