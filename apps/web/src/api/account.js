import { apiUrl } from "./client.js";
import { getAccessToken } from "../lib/auth.js";

/**
 * Load the signed-in user's profile, including their most recent reviews.
 */
export async function fetchMyAccount() {
  const token = await getAccessToken();

  if (!token) {
    throw new Error("You must be signed in");
  }

  const response = await fetch(apiUrl("/auth/me"), {
    headers: { Authorization: `Bearer ${token}` },
  });

  if (!response.ok) {
    throw new Error(`Account request failed (${response.status})`);
  }

  return response.json();
}
