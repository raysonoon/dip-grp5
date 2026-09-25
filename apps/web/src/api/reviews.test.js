import assert from "node:assert/strict";
import test from "node:test";

process.env.VITE_API_BASE_URL = "https://api.example.test/";
process.env.VITE_DEV_USER_ID = "27";

const { DEV_USER_TOKEN } = await import("./client.js");
const {
  createReview,
  deleteReview,
  fetchReviews,
  fetchVendorReviews,
  reviewImageUrl,
  updateReview,
} = await import("./reviews.js");

const REVIEW_DETAIL = {
  id: 42,
  rating: 4.5,
  comment: "Excellent food",
  created_at: "2026-09-09T08:00:00Z",
  updated_at: null,
  is_edited: false,
  user: {
    id: 2,
    display_name: "Test User",
    affiliation: "NTU",
  },
  vendor: {
    id: 7,
    name: "Test Vendor",
    location: "North Spine",
    image_url: null,
    category: "Food",
    opening_hours: "09:00 - 21:00",
  },
  images: [
    {
      id: 9,
      image_url: "/media/review_images/42/9.png",
      mime_type: "image/png",
      file_size_bytes: 1024,
      display_order: 1,
    },
  ],
};

function jsonResponse(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

test("fetchReviews fetches the homepage reviews with limit and offset", async (context) => {
  const originalFetch = globalThis.fetch;

  context.after(() => {
    globalThis.fetch = originalFetch;
  });

  globalThis.fetch = async (path, options) => {
    assert.equal(path, "/reviews?limit=15&offset=0");
    assert.equal(options.method, "GET");
    assert.equal(options.headers["X-Dev-User-Id"], undefined);

    return jsonResponse({
      items: [REVIEW_DETAIL],
      total: 1,
      limit: 15,
      offset: 0,
    });
  };

  const page = await fetchReviews(15, 0);

  assert.equal(page.items.length, 1);
  assert.equal(page.items[0].user.display_name, "Test User");
  assert.equal(page.items[0].vendor.name, "Test Vendor");
});

test("fetchVendorReviews is public, filters, and parses review details", async (context) => {
  const originalFetch = globalThis.fetch;
  context.after(() => {
    globalThis.fetch = originalFetch;
  });
  globalThis.fetch = async (path, options) => {
    assert.equal(path, "https://api.example.test/reviews?vendor_id=7");
    assert.equal(options.method, "GET");
    assert.equal(options.headers["X-Dev-User-Id"], undefined);
    return jsonResponse({ items: [REVIEW_DETAIL], total: 1, limit: 20, offset: 0 });
  };

  const page = await fetchVendorReviews(7);

  assert.deepEqual(page.items[0].user, REVIEW_DETAIL.user);
  assert.deepEqual(page.items[0].images, REVIEW_DETAIL.images);
  assert.equal(
    reviewImageUrl(42, 9),
    "https://api.example.test/reviews/42/images/9",
  );
});

test("review mutations use the test-user token and backend schemas", async (context) => {
  const originalFetch = globalThis.fetch;
  context.after(() => {
    globalThis.fetch = originalFetch;
  });
  const requests = [];
  globalThis.fetch = async (path, options) => {
    requests.push({ path, options });
    return options.method === "DELETE"
      ? new Response(null, { status: 204 })
      : jsonResponse({ id: 42 });
  };

  await createReview({ vendor_id: 7, rating: 4.5, comment: "New review" });
  await updateReview(42, { rating: 5, comment: "Updated review" });
  await deleteReview(42);

  assert.deepEqual(
    requests.map(({ path, options }) => ({
      path,
      method: options.method,
      token: options.headers["X-Dev-User-Id"],
      body: options.body,
    })),
    [
      {
        path: "https://api.example.test/reviews",
        method: "POST",
        token: DEV_USER_TOKEN,
        body: JSON.stringify({ vendor_id: 7, rating: 4.5, comment: "New review" }),
      },
      {
        path: "https://api.example.test/reviews/42",
        method: "PATCH",
        token: DEV_USER_TOKEN,
        body: JSON.stringify({ rating: 5, comment: "Updated review" }),
      },
      {
        path: "https://api.example.test/reviews/42",
        method: "DELETE",
        token: DEV_USER_TOKEN,
        body: undefined,
      },
    ],
  );
});

test("API errors expose a readable backend message", async (context) => {
  const originalFetch = globalThis.fetch;
  context.after(() => {
    globalThis.fetch = originalFetch;
  });
  globalThis.fetch = async () => jsonResponse({ detail: "You may edit only your own reviews" }, 403);

  await assert.rejects(
    updateReview(99, { comment: "Not allowed" }),
    /You may edit only your own reviews/,
  );
});
