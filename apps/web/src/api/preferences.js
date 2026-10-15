import { apiUrl } from "./client.js";
import { getAccessToken } from "../lib/auth.js";

async function authorizedRequest(path, options = {}) {
  const token = await getAccessToken();

  if (!token) {
    throw new Error("You must be signed in");
  }

  const response = await fetch(apiUrl(path), {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...options.headers,
    },
  });

  if (!response.ok) {
    throw new Error(`Preferences request failed (${response.status})`);
  }

  return response;
}

export async function fetchMyPreferences() {
  const response = await authorizedRequest("/preferences/me");
  return response.json();
}

export async function saveMyPreferences(preferences) {
  const response = await authorizedRequest("/preferences/me", {
    method: "PUT",
    body: JSON.stringify(preferences),
  });

  return response.json();
}