import { apiClient } from "./client.js";

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

export async function fetchVendorReviews(vendorId, signal) {
  const payload = await apiClient.get(`/reviews?vendor_id=${vendorId}`, { signal });
  return parseReviewList(payload);
}

export function createReview(review) {
  return apiClient.post("/reviews", review);
}

export function updateReview(reviewId, review) {
  return apiClient.patch(`/reviews/${reviewId}`, review);
}

export function deleteReview(reviewId) {
  return apiClient.delete(`/reviews/${reviewId}`);
}

export function reviewImageUrl(reviewId, imageId) {
  return `/reviews/${reviewId}/images/${imageId}`;
}
