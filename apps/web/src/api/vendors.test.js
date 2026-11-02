import assert from "node:assert/strict";
import test from "node:test";

import { fetchVendorById, fetchVendorPage, fetchVendors } from "./vendors.js";
import { apiClient } from "./client.js";
import { supabase } from "../lib/supabase.js";

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

test("fetchVendorPage forwards a custom timeout and preserves omitted defaults", async (context) => {
  const get = context.mock.method(apiClient, "get", async () => ({
    items: [], total: 0, limit: 3, offset: 0,
  }));
  const controller = new AbortController();

  await fetchVendorPage({ limit: 3, timeoutMs: 30_000, signal: controller.signal });
  await fetchVendorPage({ limit: 3 });

  assert.deepEqual(get.mock.calls[0].arguments, [
    "/vendors?limit=3&offset=0&sort=recommended",
    { auth: "optional", signal: controller.signal, timeoutMs: 30_000 },
  ]);
  assert.deepEqual(get.mock.calls[1].arguments, [
    "/vendors?limit=3&offset=0&sort=recommended",
    { auth: "optional", signal: undefined, timeoutMs: undefined },
  ]);
});

test("fetchVendors can disable auth on every page while existing calls retain auth", async (context) => {
  const descriptor = Object.getOwnPropertyDescriptor(supabase.auth, "getSession");
  Object.defineProperty(supabase.auth, "getSession", {
    configurable: true,
    value: async () => ({ data: { session: { access_token: "vendor-token" } }, error: null }),
  });
  context.after(() => {
    if (descriptor) Object.defineProperty(supabase.auth, "getSession", descriptor);
    else delete supabase.auth.getSession;
  });
  const requests = [];
  context.mock.method(globalThis, "fetch", async (path, options) => {
    requests.push({ path, options });
    const offset = Number(new URL(path, "https://example.test").searchParams.get("offset"));
    return jsonResponse({
      items: [{ ...VENDOR, id: 12 + offset }], total: 2, limit: 100, offset,
    });
  });

  const fallback = await fetchVendors("", undefined, { auth: false });
  const existing = await fetchVendors("");

  assert.deepEqual(fallback.map((vendor) => vendor.id), [12, 13]);
  assert.deepEqual(existing, fallback);
  assert.deepEqual(requests.map(({ path }) => path), [
    "/vendors?limit=100&offset=0&sort=recommended",
    "/vendors?limit=100&offset=1&sort=recommended",
    "/vendors?limit=100&offset=0&sort=recommended",
    "/vendors?limit=100&offset=1&sort=recommended",
  ]);
  assert.deepEqual(requests.map(({ options }) => options.headers.Authorization), [
    undefined, undefined, "Bearer vendor-token", "Bearer vendor-token",
  ]);
});

test("fetchVendorById finds a backend vendor by its integer id", async (context) => {
  const originalFetch = globalThis.fetch;
  context.after(() => {
    globalThis.fetch = originalFetch;
  });
  globalThis.fetch = async (path, options) => {
    assert.equal(path, "/vendors?limit=100&offset=0&sort=recommended");
    assert.equal(options.method, "GET");
    assert.equal(options.headers.Authorization, undefined);
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

test("fetchVendors returns backend vendors across pages", async (context) => {
  const originalFetch = globalThis.fetch;
  context.after(() => {
    globalThis.fetch = originalFetch;
  });
  let call = 0;
  globalThis.fetch = async () => {
    call += 1;
    if (call === 1) {
      return jsonResponse({ items: [VENDOR], total: 2, limit: 100, offset: 0 });
    }
    return jsonResponse({
      items: [{ ...VENDOR, id: 13, name: "Second Backend Vendor" }],
      total: 2,
      limit: 100,
      offset: 1,
    });
  };

  const vendors = await fetchVendors();

  assert.deepEqual(vendors.map((vendor) => vendor.id), [12, 13]);
});

test("fetchVendors sends a trimmed search query to every backend page", async (context) => {
  const originalFetch = globalThis.fetch;
  context.after(() => {
    globalThis.fetch = originalFetch;
  });
  const requestedPaths = [];
  globalThis.fetch = async (path) => {
    requestedPaths.push(path);
    if (requestedPaths.length === 1) {
      return jsonResponse({ items: [VENDOR], total: 2, limit: 100, offset: 0 });
    }
    return jsonResponse({
      items: [{ ...VENDOR, id: 13, name: "Second Backend Vendor" }],
      total: 2,
      limit: 100,
      offset: 1,
    });
  };

  await fetchVendors("  Chicken Rice  ");

  assert.deepEqual(requestedPaths, [
    "/vendors?limit=100&offset=0&q=Chicken+Rice&sort=recommended",
    "/vendors?limit=100&offset=1&q=Chicken+Rice&sort=recommended",
  ]);
});

test("fetchVendorPage repeats each multi-select filter value", async (context) => {
  const originalFetch = globalThis.fetch;
  context.after(() => {
    globalThis.fetch = originalFetch;
  });
  const requestedPaths = [];
  globalThis.fetch = async (path) => {
    requestedPaths.push(path);
    return jsonResponse({ items: [], total: 0, limit: 12, offset: 0 });
  };

  await fetchVendorPage({
    locations: ["North Spine", "South Spine"],
    categories: ["Korean"],
    cuisines: ["Japanese", "Korean"],
    limit: 12,
    offset: 0,
  });

  assert.deepEqual(requestedPaths, [
    "/vendors?limit=12&offset=0&location=North+Spine&location=South+Spine&category=Korean&cuisine=Japanese&cuisine=Korean&sort=recommended",
  ]);
});

test("fetchVendorPage sends price range, halal and vegetarian filters", async (context) => {
  const originalFetch = globalThis.fetch;
  context.after(() => {
    globalThis.fetch = originalFetch;
  });
  const requestedPaths = [];
  globalThis.fetch = async (path) => {
    requestedPaths.push(path);
    return jsonResponse({ items: [], total: 0, limit: 12, offset: 0 });
  };

  await fetchVendorPage({
    priceRanges: ["$1-10", "$20-30"],
    halal: true,
    vegetarian: true,
    limit: 12,
    offset: 0,
  });

  assert.deepEqual(requestedPaths, [
    "/vendors?limit=12&offset=0&price_range=%241-10&price_range=%2420-30&halal=true&vegetarian=true&sort=recommended",
  ]);
});

test("fetchVendorPage omits price and dietary filters when unused", async (context) => {
  const originalFetch = globalThis.fetch;
  context.after(() => {
    globalThis.fetch = originalFetch;
  });
  const requestedPaths = [];
  globalThis.fetch = async (path) => {
    requestedPaths.push(path);
    return jsonResponse({ items: [], total: 0, limit: 12, offset: 0 });
  };

  await fetchVendorPage({ limit: 12, offset: 0 });

  assert.deepEqual(requestedPaths, [
    "/vendors?limit=12&offset=0&sort=recommended",
  ]);
});
