import {
  apiClient,
  ApiAuthConfigurationError,
  ApiError,
  ApiNetworkError,
  ApiResponseError,
  ApiTimeoutError,
  apiUrl,
} from "./client.js";
import { getAccessToken } from "../lib/auth.js";

const REVIEW_AUTH_MESSAGE = "Sign in to submit a review";

function objectValue(value, label) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`Invalid ${label} in review API response`);
  }
  return value;
}

function numberValue(value, label) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new Error(`Invalid ${label} in review API response`);
  }
  return value;
}

function stringValue(value, label) {
  if (typeof value !== "string") {
    throw new Error(`Invalid ${label} in review API response`);
  }
  return value;
}

function nullableString(value, label) {
  if (value !== null && typeof value !== "string") {
    throw new Error(`Invalid ${label} in review API response`);
  }
  return value;
}

function parseReviewUser(value) {
  const user = objectValue(value, "user");
  return {
    id: numberValue(user.id, "user.id"),
    display_name: stringValue(user.display_name, "user.display_name"),
    affiliation: nullableString(user.affiliation, "user.affiliation"),
  };
}

function parseReviewVendor(value) {
  const vendor = objectValue(value, "vendor");
  return {
    id: numberValue(vendor.id, "vendor.id"),
    name: stringValue(vendor.name, "vendor.name"),
    location: nullableString(vendor.location, "vendor.location"),
    image_url: nullableString(vendor.image_url, "vendor.image_url"),
    category: nullableString(vendor.category, "vendor.category"),
    opening_hours: nullableString(vendor.opening_hours, "vendor.opening_hours"),
  };
}

function parseReviewImage(value) {
  const image = objectValue(value, "image");
  return {
    id: numberValue(image.id, "image.id"),
    image_url: stringValue(image.image_url, "image.image_url"),
    mime_type: stringValue(image.mime_type, "image.mime_type"),
    file_size_bytes: numberValue(image.file_size_bytes, "image.file_size_bytes"),
    display_order: numberValue(image.display_order, "image.display_order"),
  };
}

export function parseReviewDetail(value) {
  const review = objectValue(value, "review");
  if (!Array.isArray(review.images)) {
    throw new Error("Invalid images in review API response");
  }
  if (typeof review.is_edited !== "boolean") {
    throw new Error("Invalid is_edited in review API response");
  }

  return {
    id: numberValue(review.id, "review.id"),
    rating: numberValue(review.rating, "review.rating"),
    comment: nullableString(review.comment, "review.comment"),
    created_at: stringValue(review.created_at, "review.created_at"),
    updated_at: nullableString(review.updated_at, "review.updated_at"),
    is_edited: review.is_edited,

    upvote_count: numberValue(review.upvote_count, "review.upvote_count"),
    downvote_count: numberValue(review.downvote_count, "review.downvote_count"),
    current_user_vote: nullableString(
      review.current_user_vote,
      "review.current_user_vote",
    ),

    user: parseReviewUser(review.user),
    vendor: parseReviewVendor(review.vendor),
    images: review.images.map(parseReviewImage),
  };
}

export function parseReviewList(value) {
  const page = objectValue(value, "review list");
  if (!Array.isArray(page.items)) {
    throw new Error("Invalid items in review API response");
  }
  return {
    items: page.items.map(parseReviewDetail),
    total: numberValue(page.total, "review list total"),
    limit: numberValue(page.limit, "review list limit"),
    offset: numberValue(page.offset, "review list offset"),
  };
}

// Latest reviews across all vendors (homepage).
export async function fetchReviews(limit = 15, offset = 0, signal) {
  const payload = await apiClient.get(
    `/reviews?limit=${limit}&offset=${offset}`,
    { auth: false, signal },
  );
  return parseReviewList(payload);
}

// One page of a single vendor's reviews.
export async function fetchVendorReviews(vendorId, { limit = 10, offset = 0, signal } = {}) {
  const params = new URLSearchParams({
    vendor_id: String(vendorId),
    limit: String(limit),
    offset: String(offset),
  });
  const payload = await apiClient.get(
    `/reviews?${params.toString()}`,
    { auth: false, signal },
  );
  return parseReviewList(payload);
}

export function createReview(review) {
  return apiClient.post("/reviews", review, { authMessage: REVIEW_AUTH_MESSAGE });
}

export function updateReview(reviewId, review) {
  return apiClient.patch(`/reviews/${reviewId}`, review, { authMessage: REVIEW_AUTH_MESSAGE });
}

export function deleteReview(reviewId) {
  return apiClient.delete(`/reviews/${reviewId}`, { authMessage: REVIEW_AUTH_MESSAGE });
}

export async function voteReview(reviewId, vote) {
  const payload = await apiClient.post(
    `/reviews/${reviewId}/vote`,
    { vote },
    { authMessage: REVIEW_AUTH_MESSAGE },
  );

  const result = objectValue(payload, "review vote");

  return {
    upvote_count: numberValue(
      result.upvote_count,
      "review vote upvote_count",
    ),
    downvote_count: numberValue(
      result.downvote_count,
      "review vote downvote_count",
    ),
    current_user_vote: nullableString(
      result.current_user_vote,
      "review vote current_user_vote",
    ),
  };
}

export function reviewImageUrl(reviewId, imageId) {
  return apiUrl(`/reviews/${reviewId}/images/${imageId}`);
}

const DEFAULT_TIMEOUT_MS = 15_000;

async function multipartRequest(path, { method, formData, signal, timeoutMs = DEFAULT_TIMEOUT_MS }) {
  const accessToken = await getAccessToken();
  if (!accessToken) throw new ApiAuthConfigurationError(REVIEW_AUTH_MESSAGE);
  const headers = { Authorization: `Bearer ${accessToken}` };

  const controller = new AbortController();
  let timedOut = false;
  const timeoutId = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  const abortFromCaller = () => controller.abort(signal?.reason);
  if (signal?.aborted) abortFromCaller();
  else signal?.addEventListener("abort", abortFromCaller, { once: true });

  let response;
  try {
    response = await fetch(apiUrl(path), {
      method,
      headers,
      body: formData,
      signal: controller.signal,
    });
  } catch (error) {
    if (timedOut) throw new ApiTimeoutError(timeoutMs);
    if (signal?.aborted) throw error;
    throw new ApiNetworkError("Could not connect to the API", error);
  } finally {
    clearTimeout(timeoutId);
    signal?.removeEventListener("abort", abortFromCaller);
  }

  let payload = null;
  if (response.status !== 204) {
    const contentType = response.headers.get("content-type") ?? "";
    try {
      payload = contentType.includes("application/json")
        ? await response.json()
        : await response.text();
    } catch (error) {
      throw new ApiResponseError("API response body is malformed", response.status, error);
    }
  }

  if (!response.ok) {
    const message =
      typeof payload?.detail === "string"
        ? payload.detail
        : Array.isArray(payload?.detail)
          ? payload.detail.map((issue) => issue?.msg).filter(Boolean).join(", ")
          : `Request failed with status ${response.status}`;
    throw new ApiError(message, response.status, payload);
  }
  return payload;
}

export async function uploadReviewImage(reviewId, file, signal) {
  const formData = new FormData();
  formData.append("file", file);
  const payload = await multipartRequest(`/reviews/${reviewId}/images`, {
    method: "POST",
    formData,
    signal,
  });
  return parseReviewImage(payload);
}

export async function deleteReviewImage(reviewId, imageId, signal) {
  return multipartRequest(`/reviews/${reviewId}/images/${imageId}`, {
    method: "DELETE",
    formData: undefined,
    signal,
  });
}

export async function reorderReviewImage(reviewId, imageId, displayOrder, signal) {
  const formData = new FormData();
  formData.append("display_order", String(displayOrder));
  const payload = await multipartRequest(`/reviews/${reviewId}/images/${imageId}`, {
    method: "PATCH",
    formData,
    signal,
  });
  return parseReviewImage(payload);
}