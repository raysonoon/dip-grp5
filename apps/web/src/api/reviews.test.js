import assert from "node:assert/strict";
import test from "node:test";

process.env.VITE_API_BASE_URL = "https://api.example.test/";

const {
  createReview,
  deleteReview,
  fetchReviews,
  fetchVendorReviews,
  reviewImageUrl,
  updateReview,
} = await import("./reviews.js");
const { supabase } = await import("../lib/supabase.js");

function configureSession(context, accessToken = "test-access-token") {
  const originalDescriptor = Object.getOwnPropertyDescriptor(
    supabase.auth,
    "getSession",
  );
  Object.defineProperty(supabase.auth, "getSession", {
    configurable: true,
    value: async () => ({
    data: { session: { access_token: accessToken } },
    error: null,
    }),
  });
  context.after(() => {
    if (originalDescriptor) {
      Object.defineProperty(supabase.auth, "getSession", originalDescriptor);
    } else {
      delete supabase.auth.getSession;
    }
  });
}

const REVIEW_DETAIL = {
  id: 42,
  rating: 4.5,
  comment: "Excellent food",
  created_at: "2026-09-09T08:00:00Z",
  updated_at: null,
  is_edited: false,
  upvote_count: 0,
  downvote_count: 0,
  current_user_vote: null,
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
    assert.equal(path, "https://api.example.test/reviews?limit=15&offset=0");
    assert.equal(options.method, "GET");
    assert.equal(options.headers.Authorization, undefined);

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
    assert.equal(
      path,
      "https://api.example.test/reviews?vendor_id=7&limit=10&offset=0",
    );
    assert.equal(options.method, "GET");
    assert.equal(options.headers.Authorization, undefined);
    return jsonResponse({ items: [REVIEW_DETAIL], total: 1, limit: 10, offset: 0 });
  };

  const page = await fetchVendorReviews(7);

  assert.deepEqual(page.items[0].user, REVIEW_DETAIL.user);
  assert.deepEqual(page.items[0].images, REVIEW_DETAIL.images);
  assert.equal(
    reviewImageUrl(42, 9),
    "https://api.example.test/reviews/42/images/9",
  );
});

test("fetchVendorReviews sends the requested limit and offset", async (context) => {
  const originalFetch = globalThis.fetch;
  context.after(() => {
    globalThis.fetch = originalFetch;
  });
  globalThis.fetch = async (path) => {
    assert.equal(
      path,
      "https://api.example.test/reviews?vendor_id=7&limit=10&offset=20",
    );
    return jsonResponse({ items: [REVIEW_DETAIL], total: 21, limit: 10, offset: 20 });
  };

  const page = await fetchVendorReviews(7, { limit: 10, offset: 20 });

  assert.equal(page.offset, 20);
  assert.equal(page.total, 21);
});

test("review mutations use the test-user token and backend schemas", async (context) => {
  configureSession(context, "27");
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
      token: options.headers.Authorization,
      body: options.body,
    })),
    [
      {
        path: "https://api.example.test/reviews",
        method: "POST",
        token: "Bearer 27",
        body: JSON.stringify({ vendor_id: 7, rating: 4.5, comment: "New review" }),
      },
      {
        path: "https://api.example.test/reviews/42",
        method: "PATCH",
        token: "Bearer 27",
        body: JSON.stringify({ rating: 5, comment: "Updated review" }),
      },
      {
        path: "https://api.example.test/reviews/42",
        method: "DELETE",
        token: "Bearer 27",
        body: undefined,
      },
    ],
  );
});

test("API errors expose a readable backend message", async (context) => {
  configureSession(context, "27");
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

for (const sort of ["newest", "oldest", "best", "controversial"]) {
  test(`fetchVendorReviews requests server sorting: ${sort}`, async (context) => {
    const originalFetch = globalThis.fetch;
    context.after(() => { globalThis.fetch = originalFetch; });
    globalThis.fetch = async (path) => {
      const params = new URL(path).searchParams;
      assert.equal(params.get("sort"), sort);
      assert.equal(params.get("vendor_id"), "7");
      assert.equal(params.get("offset"), "10");
      // Keep the server's order, even when it differs from chronological order.
      return jsonResponse({
        items: [REVIEW_DETAIL, { ...REVIEW_DETAIL, id: 43, created_at: "2026-09-10T08:00:00Z" }],
        total: 12, limit: 10, offset: 10,
      });
    };
    const page = await fetchVendorReviews(7, { sort, offset: 10 });
    assert.deepEqual(page.items.map((review) => review.id), [42, 43]);
    assert.equal(page.total, 12);
  });
}

for (const media of ["all", "with_photos", "without_photos"]) {
  test(`fetchVendorReviews combines rating and media: ${media}`, async (context) => {
    const originalFetch = globalThis.fetch;
    context.after(() => { globalThis.fetch = originalFetch; });
    globalThis.fetch = async (path) => {
      const params = new URL(path).searchParams;
      assert.equal(params.get("sort"), "best");
      assert.equal(params.get("rating"), "4.5");
      assert.equal(params.get("media"), media);
      assert.equal(params.get("limit"), "5");
      return jsonResponse({ items: [REVIEW_DETAIL], total: 1, limit: 5, offset: 0 });
    };
    await fetchVendorReviews(7, { sort: "best", rating: 4.5, media, limit: 5 });
  });
}

for (const rating of [undefined, null, ""]) {
  test(`fetchVendorReviews omits an unset rating (${JSON.stringify(rating)})`, async (context) => {
    const originalFetch = globalThis.fetch;
    context.after(() => { globalThis.fetch = originalFetch; });
    globalThis.fetch = async (path) => {
      assert.equal(new URL(path).searchParams.has("rating"), false);
      return jsonResponse({ items: [], total: 0, limit: 10, offset: 0 });
    };
    await fetchVendorReviews(7, { rating });
  });
}

test("fetchVendorReviews supports the lowest half-star filter", async (context) => {
  const originalFetch = globalThis.fetch;
  context.after(() => { globalThis.fetch = originalFetch; });
  globalThis.fetch = async (path) => {
    assert.equal(new URL(path).searchParams.get("rating"), "0.5");
    return jsonResponse({ items: [], total: 0, limit: 10, offset: 0 });
  };
  await fetchVendorReviews(7, { rating: "0.5" });
});

test("fetchVendorReviews preserves homepage limit/signal calls and cancellation", async (context) => {
  const originalFetch = globalThis.fetch;
  context.after(() => { globalThis.fetch = originalFetch; });
  const controller = new AbortController();
  globalThis.fetch = async (path, options) => {
    assert.equal(path, "https://api.example.test/reviews?vendor_id=7&limit=3&offset=0");
    assert.equal(options.signal.aborted, false);
    controller.abort();
    assert.equal(options.signal.aborted, true);
    throw new DOMException("Aborted", "AbortError");
  };
  await assert.rejects(fetchVendorReviews(7, { limit: 3, signal: controller.signal }), { name: "AbortError" });
});

test("fetchVendorReviews sends optional auth to preserve the current user's vote", async (context) => {
  configureSession(context, "27");
  const originalFetch = globalThis.fetch;
  context.after(() => { globalThis.fetch = originalFetch; });
  globalThis.fetch = async (_path, options) => {
    assert.equal(options.headers.Authorization, "Bearer 27");
    return jsonResponse({ items: [{ ...REVIEW_DETAIL, current_user_vote: "up" }], total: 1, limit: 10, offset: 0 });
  };
  const page = await fetchVendorReviews(7, { sort: "best" });
  assert.equal(page.items[0].current_user_vote, "up");
});
