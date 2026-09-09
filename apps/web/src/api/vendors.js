import { apiClient } from "./client.js";

function objectValue(value, label) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`Invalid ${label} in vendor API response`);
  }
  return value;
}

function numberValue(value, label) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new Error(`Invalid ${label} in vendor API response`);
  }
  return value;
}

function stringValue(value, label) {
  if (typeof value !== "string") {
    throw new Error(`Invalid ${label} in vendor API response`);
  }
  return value;
}

function nullableString(value, label) {
  if (value !== null && typeof value !== "string") {
    throw new Error(`Invalid ${label} in vendor API response`);
  }
  return value;
}

function nullableNumber(value, label) {
  if (value !== null && (typeof value !== "number" || !Number.isFinite(value))) {
    throw new Error(`Invalid ${label} in vendor API response`);
  }
  return value;
}

function nullableBoolean(value, label) {
  if (value !== null && typeof value !== "boolean") {
    throw new Error(`Invalid ${label} in vendor API response`);
  }
  return value;
}

function parseVendorImage(value) {
  const image = objectValue(value, "vendor image");
  return {
    id: numberValue(image.id, "vendor image id"),
    vendor_id: numberValue(image.vendor_id, "vendor image vendor_id"),
    image_url: stringValue(image.image_url, "vendor image image_url"),
    mime_type: stringValue(image.mime_type, "vendor image mime_type"),
    file_size_bytes: numberValue(image.file_size_bytes, "vendor image file_size_bytes"),
    display_order: numberValue(image.display_order, "vendor image display_order"),
    created_at: stringValue(image.created_at, "vendor image created_at"),
  };
}

export function parseVendor(value) {
  const vendor = objectValue(value, "vendor");
  if (!Array.isArray(vendor.images)) {
    throw new Error("Invalid images in vendor API response");
  }
  return {
    id: numberValue(vendor.id, "vendor id"),
    name: stringValue(vendor.name, "vendor name"),
    location: nullableString(vendor.location, "vendor location"),
    unit_code: nullableString(vendor.unit_code, "vendor unit_code"),
    image_url: nullableString(vendor.image_url, "vendor image_url"),
    category: nullableString(vendor.category, "vendor category"),
    opening_hours: nullableString(vendor.opening_hours, "vendor opening_hours"),
    price_range: nullableString(vendor.price_range, "vendor price_range"),
    halal: nullableBoolean(vendor.halal, "vendor halal"),
    vegetarian: nullableBoolean(vendor.vegetarian, "vendor vegetarian"),
    average_google_rating: nullableNumber(
      vendor.average_google_rating,
      "vendor average_google_rating",
    ),
    average_rating: nullableNumber(vendor.average_rating, "vendor average_rating"),
    review_count: numberValue(vendor.review_count, "vendor review_count"),
    created_at: stringValue(vendor.created_at, "vendor created_at"),
    updated_at: stringValue(vendor.updated_at, "vendor updated_at"),
    images: vendor.images.map(parseVendorImage),
  };
}

export function parseVendorList(value) {
  const page = objectValue(value, "vendor list");
  if (!Array.isArray(page.items)) {
    throw new Error("Invalid items in vendor API response");
  }
  return {
    items: page.items.map(parseVendor),
    total: numberValue(page.total, "vendor list total"),
    limit: numberValue(page.limit, "vendor list limit"),
    offset: numberValue(page.offset, "vendor list offset"),
  };
}

export async function fetchVendorById(vendorId, signal) {
  let offset = 0;
  const limit = 100;

  while (true) {
    const payload = await apiClient.get(
      `/vendors?limit=${limit}&offset=${offset}`,
      { signal },
    );
    const page = parseVendorList(payload);
    const vendor = page.items.find((item) => item.id === vendorId);
    if (vendor) return vendor;

    offset += page.items.length;
    if (page.items.length === 0 || offset >= page.total) {
      throw new Error("Vendor not found");
    }
  }
}
