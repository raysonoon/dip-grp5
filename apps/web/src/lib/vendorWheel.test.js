import assert from "node:assert/strict";
import test from "node:test";
import { chooseWheelSpin, completeWheelVendor, createWheelSession, visibleResultsForWheel, wheelSessionReducer, wheelVendorLabel } from "./vendorWheel.js";

const source = (id, type = "vendor", fields = {}) => ({ source_type: type, vendor_id: id, vendor_name: `Place ${id}`, ...fields });
const merge = (state, ...sources) => wheelSessionReducer(state, { type: "sources", sources });
const ids = (state) => state.vendors.map((vendor) => vendor.id);

test("the pool accumulates SQL, Reddit and Google vendors across responses, deduplicated by id", () => {
  let state = merge(createWheelSession(), source(1), source(1, "reddit"));
  assert.deepEqual(ids(state), [1]);
  state = merge(state, source(2, "google_review"), source(3, "reddit"), source(1));
  assert.deepEqual(ids(state), [1, 2, 3]);
  assert.deepEqual(ids(merge(state)), [1, 2, 3]);
});

test("counts, unrelated sources and invalid vendor ids never enter the pool", () => {
  const state = merge(createWheelSession(), null, {}, [], source(1, "count"), source(2, "dish"),
    source(null, "reddit"), source("3"), source(-1), source(0), source(2.3), source(Infinity), source(NaN), source(4));
  assert.deepEqual(ids(state), [4]);
});

test("source identity is the vendor id, even when distinct vendors have the same name", () => {
  const state = merge(createWheelSession(), source(1, "vendor", { vendor_name: "Same" }), source(2, "reddit", { vendor_name: "Same" }));
  assert.equal(state.vendors.length, 2);
});

test("sparse review sources do not erase SQL metadata, including a zero rating", () => {
  const first = merge(createWheelSession(), source(1, "vendor", { location: "Hall 1", category: "Cafe", rating: 0 }));
  const next = merge(first, source(1, "reddit", { vendor_name: null, location: "", rating: null }));
  assert.deepEqual(next.vendors, first.vendors);
  assert.equal(first.vendors[0].rating, 0);
});

test("removing a winner persists across later mentions and does not mutate prior state", () => {
  const before = merge(createWheelSession(), source(1), source(2), source(3));
  const after = wheelSessionReducer(before, { type: "remove", vendorId: 2 });
  assert.deepEqual(ids(before), [1, 2, 3]);
  assert.deepEqual(ids(merge(after, source(2, "reddit"), source(4))), [1, 3, 4]);
  assert.deepEqual(after.excludedIds, [2]);
});

test("the last two vendors can reduce to one, then removal is disabled", () => {
  const state = merge(createWheelSession(), source(1), source(2));
  assert.equal(wheelSessionReducer(state, { type: "remove", vendorId: 99 }), state);
  const last = wheelSessionReducer(state, { type: "remove", vendorId: 1 });
  assert.deepEqual(ids(last), [2]);
  assert.equal(wheelSessionReducer(last, { type: "remove", vendorId: 2 }), last);
});

test("a place removed before any spin is excluded from every subsequent spin and source update", () => {
  let state = merge(createWheelSession(), source(1), source(2), source(3));
  state = wheelSessionReducer(state, { type: "remove", vendorId: 2 });
  state = merge(state, source(2, "google_review"));
  let rotation = 0;
  for (const random of [0, 0.25, 0.5, 0.75, 1 - Number.EPSILON]) {
    const spin = chooseWheelSpin(state.vendors, rotation, random);
    assert.notEqual(spin.vendor.id, 2);
    const pointedIndex = Math.floor(((360 - spin.rotation % 360) % 360) / (360 / state.vendors.length));
    assert.equal(state.vendors[pointedIndex].id, spin.vendor.id);
    rotation = spin.rotation;
  }
});

test("sparse and dense wheel labels retain names, truncating long names without splitting Unicode characters", () => {
  for (const count of [1, 8, 9, 30, 60]) {
    assert.equal(wheelVendorLabel("Gelare", count), "Gelare");
    const longLabel = wheelVendorLabel("A very long campus vendor name", count);
    assert.ok(longLabel.startsWith("A very"));
    assert.ok(longLabel.endsWith("..."));
    assert.ok(Array.from(longLabel).length <= 17);
  }
  assert.equal(wheelVendorLabel("🍜🍜🍜🍜🍜🍜🍜🍜🍜🍜🍜🍜🍜", 60), "🍜🍜🍜🍜🍜🍜🍜🍜🍜...");
});

test("a new session clears both the accumulated pool and all exclusions", () => {
  let state = merge(createWheelSession(), source(1), source(2), source(3));
  state = wheelSessionReducer(state, { type: "remove", vendorId: 1 });
  state = wheelSessionReducer(state, { type: "reset" });
  assert.deepEqual(state, createWheelSession());
  assert.deepEqual(ids(merge(state, source(1))), [1]);
});

test("the candidate pool is independent of bounded conversation history", () => {
  let state = createWheelSession();
  for (let id = 1; id <= 60; id++) state = merge(state, source(id));
  assert.equal(state.vendors.length, 60);
  assert.equal(state.vendors[0].id, 1);
});

test("every sector can win and every stop lands the winner beneath the pointer", () => {
  for (const count of [1, 2, 3, 7, 30]) {
    const vendors = Array.from({ length: count }, (_, i) => source(i + 1)).map((item) => ({ id: item.vendor_id, name: item.vendor_name, location: null, category: null, rating: null }));
    let angle = 0;
    vendors.forEach((vendor, index) => {
      const spin = chooseWheelSpin(vendors, angle, (index + 0.5) / count);
      assert.equal(spin.vendor.id, vendor.id);
      const pointedIndex = Math.floor(((360 - spin.rotation % 360) % 360) / (360 / count));
      assert.equal(pointedIndex, index);
      assert.ok(spin.rotation >= angle + 1800);
      angle = spin.rotation;
    });
    assert.equal(chooseWheelSpin(vendors, 0, 0).vendor.id, 1);
    assert.equal(chooseWheelSpin(vendors, 0, 1 - Number.EPSILON).vendor.id, count);
  }
});

test("empty wheels and invalid random values cannot spin", () => {
  assert.throws(() => chooseWheelSpin([]));
  const vendors = merge(createWheelSession(), source(1), source(2)).vendors;
  assert.equal(chooseWheelSpin(vendors.slice(0, 1)).vendor.id, 1);
  for (const random of [-1, 1, Infinity, NaN]) assert.throws(() => chooseWheelSpin(vendors, 0, random));
});

test("catalog details enrich sparse review entries without adding unrelated candidates", () => {
  const vendor = merge(createWheelSession(), source(8, "google_review", { vendor_name: null })).vendors[0];
  const details = completeWheelVendor(vendor, [
    { id: 99, name: "Unrelated" },
    { id: 8, name: "Real cafe", location: "Hall 8", category: "Cafe", average_rating: 0, average_google_rating: 4.7 },
  ]);
  assert.deepEqual(details, { id: 8, name: "Real cafe", location: "Hall 8", category: "Cafe", rating: 0 });
  assert.equal(vendor.name, "Vendor 8");
  assert.equal(completeWheelVendor(vendor, []), vendor);
});

test("Discover uses only the visible ranked results, including places revealed by Show more", () => {
  const results = Object.freeze(Array.from({ length: 28 }, (_, index) => Object.freeze({
    id: 80 - index,
    name: `Campus place ${80 - index}`,
    location: "Selected area",
    category: "Cafe",
    average_rating: null,
    average_google_rating: 4.1,
    discovery_distance_m: index * 100,
  })));
  const firstPage = visibleResultsForWheel(results, 12);
  const expanded = visibleResultsForWheel(results, 24);
  assert.deepEqual(firstPage.map((vendor) => vendor.id), results.slice(0, 12).map((vendor) => vendor.id));
  assert.deepEqual(expanded.map((vendor) => vendor.id), results.slice(0, 24).map((vendor) => vendor.id));
  assert.equal(visibleResultsForWheel(results, 36).length, 28);
  assert.deepEqual(visibleResultsForWheel(results, 0), []);
  assert.deepEqual(visibleResultsForWheel([], 12), []);
  assert.equal(results.length, 28);
});

test("Discover maps live vendor details and prefers a valid community rating, including zero", () => {
  const results = [
    { id: 71, name: "New local kitchen", location: " Hall 1 ", category: " Restaurant ", average_rating: 0, average_google_rating: 4.9 },
    { id: 72, name: "Another kitchen", location: null, category: "", average_rating: null, average_google_rating: 4.3 },
    { id: 73, name: "Unrated kitchen", average_rating: null, average_google_rating: null },
  ];
  assert.deepEqual(visibleResultsForWheel(results, 12), [
    { id: 71, name: "New local kitchen", location: "Hall 1", category: "Restaurant", rating: 0 },
    { id: 72, name: "Another kitchen", location: null, category: null, rating: 4.3 },
    { id: 73, name: "Unrated kitchen", location: null, category: null, rating: null },
  ]);
});

test("Discover removals stay local to an opening and reopening resets from the current visible results", () => {
  const results = [31, 27, 42, 99].map((id) => Object.freeze({ id, name: `Independent place ${id}` }));
  const before = createWheelSession(visibleResultsForWheel(results, 3));
  const removed = wheelSessionReducer(before, { type: "remove", vendorId: 27 });
  assert.deepEqual(ids(removed), [31, 42]);
  assert.deepEqual(ids(before), [31, 27, 42]);
  assert.deepEqual(results.map((vendor) => vendor.id), [31, 27, 42, 99]);
  assert.deepEqual(removed.excludedIds, [27]);

  const reopened = createWheelSession(visibleResultsForWheel(results, 4));
  assert.deepEqual(ids(reopened), [31, 27, 42, 99]);
  assert.deepEqual(reopened.excludedIds, []);
  const changedPreferences = createWheelSession(visibleResultsForWheel([results[3], results[1]], 12));
  assert.deepEqual(ids(changedPreferences), [99, 27]);
  assert.deepEqual(changedPreferences.excludedIds, []);
});
