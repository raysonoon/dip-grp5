import assert from "node:assert/strict";
import test from "node:test";

process.env.VITE_API_BASE_URL = "https://api.example.test/";
const { favouriteVendor, fetchMyFavourites, fetchVendorFavourite, unfavouriteVendor } = await import("./favourites.js");
const { supabase } = await import("../lib/supabase.js");

function configureSession(context, token = "test-favourite-token") {
  const descriptor = Object.getOwnPropertyDescriptor(supabase.auth, "getSession");
  Object.defineProperty(supabase.auth, "getSession", {
    configurable: true,
    value: async () => ({ data: { session: token ? { access_token: token } : null }, error: null }),
  });
  context.after(() => {
    if (descriptor) Object.defineProperty(supabase.auth, "getSession", descriptor);
    else delete supabase.auth.getSession;
  });
}

test("favourites use authenticated, paginated list and per-vendor routes", async (context) => {
  configureSession(context);
  const requests = [];
  context.mock.method(globalThis, "fetch", async (url, options) => {
    requests.push({ url, options });
    if (options.method === "DELETE") return new Response(null, { status: 204 });
    const result = url.includes("?")
      ? { items: [{ vendor: { id: 7, name: "Saved Stall" }, created_at: "2026-10-25T08:00:00Z" }], total: 6, limit: 5, offset: 5 }
      : { vendor_id: 7, favourited: true, created_at: "2026-10-25T08:00:00Z" };
    return Response.json(result);
  });
  const page = await fetchMyFavourites({ limit: 5, offset: 5 });
  assert.equal(page.total, 6);
  assert.equal(page.items[0].vendor.name, "Saved Stall");
  assert.equal((await fetchVendorFavourite(7)).favourited, true);
  assert.equal((await favouriteVendor(7)).vendor_id, 7);
  assert.equal(await unfavouriteVendor(7), null);
  assert.deepEqual(requests.map(({ url, options }) => [url, options.method]), [
    ["https://api.example.test/auth/me/favourites?limit=5&offset=5", "GET"],
    ["https://api.example.test/auth/me/favourites/7", "GET"],
    ["https://api.example.test/auth/me/favourites/7", "PUT"],
    ["https://api.example.test/auth/me/favourites/7", "DELETE"],
  ]);
  assert.ok(requests.every(({ options }) => options.headers.Authorization === "Bearer test-favourite-token"));
});

test("guests cannot read or change favourites and send no API requests", async (context) => {
  configureSession(context, null);
  const fetch = context.mock.method(globalThis, "fetch", async () => { throw new Error("Unexpected request"); });
  for (const request of [fetchMyFavourites, () => fetchVendorFavourite(7), () => favouriteVendor(7), () => unfavouriteVendor(7)]) {
    await assert.rejects(request, { name: "ApiAuthConfigurationError" });
  }
  assert.equal(fetch.mock.callCount(), 0);
});

test("favourite API failures reject instead of reporting a saved state", async (context) => {
  configureSession(context);
  context.mock.method(globalThis, "fetch", async () => Response.json({ detail: "Vendor not found" }, { status: 404 }));
  await assert.rejects(() => favouriteVendor(99), { name: "ApiError", status: 404, message: "Vendor not found" });
});
