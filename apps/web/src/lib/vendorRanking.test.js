import assert from "node:assert/strict";
import test from "node:test";

import {
  formatDistance,
  rankVendors,
  sortByRating,
  vendorRating,
} from "./vendorRanking.js";

const NEAR = { id: 1, name: "Near", distance_m: 200, average_rating: 3, average_google_rating: null };
const FAR = { id: 2, name: "Far", distance_m: 1500, average_rating: null, average_google_rating: 5 };
const UNRATED = { id: 3, name: "Unrated", distance_m: 100, average_rating: null, average_google_rating: null };

const ids = (vendors) => vendors.map((vendor) => vendor.id);
const options = { maxDistanceM: 2000 };

test("prioritising distance puts the closest vendor first", () => {
  assert.deepEqual(ids(rankVendors([FAR, NEAR], { ...options, distanceWeight: 1 })), [1, 2]);
});

test("prioritising rating puts the best rated vendor first", () => {
  assert.deepEqual(ids(rankVendors([NEAR, FAR], { ...options, distanceWeight: 0 })), [2, 1]);
});

test("an unrated vendor ranks last when only rating matters", () => {
  assert.deepEqual(
    ids(rankVendors([UNRATED, NEAR, FAR], { ...options, distanceWeight: 0 })),
    [2, 1, 3],
  );
});

test("vendorRating prefers the app rating over the Google rating", () => {
  assert.equal(vendorRating({ average_rating: 4, average_google_rating: 5 }), 4);
  assert.equal(vendorRating({ average_rating: null, average_google_rating: 5 }), 5);
  assert.equal(vendorRating({ average_rating: null, average_google_rating: null }), null);
});

test("sortByRating orders best first with unrated last", () => {
  assert.deepEqual(ids(sortByRating([UNRATED, NEAR, FAR])), [2, 1, 3]);
});

test("formatDistance uses metres below 1 km and km above", () => {
  assert.equal(formatDistance(420.4), "420 m");
  assert.equal(formatDistance(1500), "1.5 km");
  assert.equal(formatDistance(null), "");
});