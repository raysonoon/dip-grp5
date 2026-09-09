import assert from "node:assert/strict";
import test from "node:test";

import { TEST_USER_TOKEN } from "./client.js";
import { fetchVendorById } from "./vendors.js";

const VENDOR = {
  id: 12,
  name: "Backend Vendor Name",
  location: "North Spine",
  unit_code: "NS-12",
  image_url: null,
  category: "Japanese",
  opening_hours: "09:00 - 21:00",
  price_range: "$$",
  halal: false,
  vegetarian: null,
  average_google_rating: 4.7,
  average_rating: 4.5,
  review_count: 3,
  created_at: "2026-09-09T08:00:00Z",
  updated_at: "2026-09-09T08:00:00Z",
  images: [],
};

function jsonResponse(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

test("fetchVendorById finds a backend vendor by its integer id", async (context) => {
  const originalFetch = globalThis.fetch;
  context.after(() => {
    globalThis.fetch = originalFetch;
  });
  globalThis.fetch = async (path, options) => {
    assert.equal(path, "/vendors?limit=100&offset=0");
    assert.equal(options.method, "GET");
    assert.equal(options.headers["X-Dev-User-Id"], TEST_USER_TOKEN);
    return jsonResponse({ items: [VENDOR], total: 1, limit: 100, offset: 0 });
  };

  const vendor = await fetchVendorById(12);

  assert.equal(vendor.id, 12);
  assert.equal(vendor.name, "Backend Vendor Name");
  assert.equal(vendor.average_rating, 4.5);
});

test("fetchVendorById reports a missing vendor without crashing", async (context) => {
  const originalFetch = globalThis.fetch;
  context.after(() => {
    globalThis.fetch = originalFetch;
  });
  globalThis.fetch = async () => jsonResponse({ items: [], total: 0, limit: 100, offset: 0 });

  await assert.rejects(fetchVendorById(999), /Vendor not found/);
});
