import { apiClient } from "./client.js";

const FAVOURITES_PATH = "/auth/me/favourites";

/** @param {{ limit?: number, offset?: number, signal?: AbortSignal }} options */
export function fetchMyFavourites({ limit = 5, offset = 0, signal } = {}) {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  return apiClient.get(`${FAVOURITES_PATH}?${params}`, { signal });
}

export function fetchVendorFavourite(vendorId, signal) {
  return apiClient.get(`${FAVOURITES_PATH}/${vendorId}`, { signal });
}

export function favouriteVendor(vendorId) {
  return apiClient.put(`${FAVOURITES_PATH}/${vendorId}`);
}

export function unfavouriteVendor(vendorId) {
  return apiClient.delete(`${FAVOURITES_PATH}/${vendorId}`);
}
