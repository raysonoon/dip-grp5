import assert from "node:assert/strict";
import test from "node:test";
import { guestDiscoveryOptions, recommendGuestVendors } from "./guestDiscovery.js";

const vendor = (id, fields = {}) => ({
  id, name: `Vendor ${id}`, category: "Chinese restaurant", location: "North Spine",
  halal: null, vegetarian: null, average_rating: null, average_google_rating: null,
  ...fields,
});
const ids = (vendors) => vendors.map((item) => item.id);

test("food and location choices prioritise matching vendors without removing alternatives", () => {
  const catalog = [
    vendor(1, { halal: true, vegetarian: true }),
    vendor(2, { halal: true, vegetarian: false }),
    vendor(3, { halal: true, vegetarian: true, location: "South Spine" }),
    vendor(4, { halal: true, vegetarian: true, category: "Cafe" }),
  ];
  const result = ids(recommendGuestVendors(catalog, {
    categories: ["Chinese restaurant"], locations: ["North Spine"], halal: true, vegetarian: true,
  }));
  assert.equal(result[0], 1);
  assert.deepEqual([...result].sort(), [1, 3, 4]);
});

test("multiple food types and locations prioritise any choice within each group, while dietary requirements still apply", () => {
  const catalog = [
    vendor(1, { halal: true, vegetarian: true }),
    vendor(2, { category: "Cafe", location: "South Spine", halal: true, vegetarian: true }),
    vendor(3, { category: "Pasta shop", halal: true, vegetarian: true }),
    vendor(4, { location: "Hall 1", halal: true, vegetarian: true }),
    vendor(5, { category: "Cafe", halal: false, vegetarian: true }),
    vendor(6, { location: "South Spine", halal: true, vegetarian: false }),
  ];
  assert.deepEqual(ids(recommendGuestVendors(catalog, {
    categories: ["Chinese restaurant", "Cafe"], locations: ["North Spine", "South Spine"],
    halal: true, vegetarian: true,
  })), [1, 2, 3, 4]);
});

test("unknown dietary information does not satisfy a selected dietary requirement", () => {
  assert.deepEqual(recommendGuestVendors([vendor(1)], { halal: true }), []);
  assert.deepEqual(recommendGuestVendors([vendor(1)], { vegetarian: true }), []);
});

test("Hall 1 receives the selected-area boost while Hall 11 remains available", () => {
  const catalog = [vendor(1, { location: "Hall 1" }), vendor(2, { location: "Hall 11" })];
  const result = recommendGuestVendors(catalog, { locations: ["Hall 1"] });
  assert.deepEqual(ids(result), [1, 2]);
  assert.equal(result[0].discovery_location_match, true);
  assert.equal(result[1].discovery_location_match, false);
});

test("a food type with no exact match still leaves other campus vendors available", () => {
  const result = recommendGuestVendors([vendor(1)], { categories: ["Pasta shop"] });
  assert.deepEqual(ids(result), [1]);
  assert.equal(result[0].discovery_category_match, false);
});

test("open preferences show all real vendors, with rated results first and no input mutation", () => {
  const catalog = [
    vendor(1), vendor(2, { average_google_rating: 4.2 }),
    vendor(3, { average_rating: 4.8 }), vendor(4, { category: "Demo" }),
  ];
  assert.deepEqual(ids(recommendGuestVendors(catalog)), [3, 2, 1]);
  assert.deepEqual(ids(catalog), [1, 2, 3, 4]);
});

test("nearby places outside a selected area's exact label stay visible and sort by distance", () => {
  const catalog = [
    vendor(1, { location: "Chosen area", map_coordinates: { lat: 1.35, lng: 103.68 } }),
    vendor(2, { location: "Next door", map_coordinates: { lat: 1.351, lng: 103.68 } }),
    vendor(3, { location: "Further away", map_coordinates: { lat: 1.36, lng: 103.68 } }),
  ];
  const result = recommendGuestVendors([catalog[2], catalog[0], catalog[1]], { locations: ["Chosen area"] });
  assert.deepEqual(ids(result), [1, 2, 3]);
  assert.ok(Math.abs(result[1].discovery_distance_m - 111.2) < 1);
  assert.ok(result[2].discovery_distance_m > 1000);
});

test("distance uses the closest selected area rather than the average of different areas", () => {
  const catalog = [
    vendor(1, { location: "Area A", map_coordinates: { lat: 1.35, lng: 103.68 } }),
    vendor(2, { location: "Area B", map_coordinates: { lat: 1.36, lng: 103.68 } }),
    vendor(3, { location: "Nearby B", map_coordinates: { lat: 1.3601, lng: 103.68 } }),
  ];
  const result = recommendGuestVendors(catalog, { locations: ["Area A", "Area B"] });
  assert.ok(result.find((item) => item.id === 3).discovery_distance_m < 12);
  assert.equal(result.length, 3);
});

test("cuisine and proximity both matter, without hiding a far-away food match or a nearby alternative", () => {
  const catalog = [
    vendor(1, { category: "Drinks", location: "Area A", map_coordinates: { lat: 1.35, lng: 103.68 } }),
    vendor(2, { category: "Pasta shop", location: "Next door", map_coordinates: { lat: 1.3501, lng: 103.68 } }),
    vendor(3, { category: "Pasta shop", location: "Far away", map_coordinates: { lat: 1.38, lng: 103.68 } }),
    vendor(4, { category: "Cafe", location: "Nearby", map_coordinates: { lat: 1.3505, lng: 103.68 } }),
  ];
  const result = ids(recommendGuestVendors(catalog, { categories: ["Pasta shop"], locations: ["Area A"] }));
  assert.equal(result[0], 2);
  assert.ok(result.indexOf(4) < result.indexOf(3));
  assert.deepEqual([...result].sort(), [1, 2, 3, 4]);
});

test("missing coordinates remain visible without inventing a distance", () => {
  const catalog = [vendor(1, { location: "No coordinates" }), vendor(2)];
  const result = recommendGuestVendors(catalog, { locations: ["No coordinates"] });
  assert.deepEqual(ids(result), [1, 2]);
  assert.ok(result.every((item) => item.discovery_distance_m === null));
});

test("a vendor with missing coordinates does not outrank measured nearby places just for its area label", () => {
  const catalog = [
    vendor(1, { location: "Area A", average_rating: 5 }),
    vendor(2, { location: "Area A", map_coordinates: { lat: 1.35, lng: 103.68 } }),
    vendor(3, { location: "Nearby A", map_coordinates: { lat: 1.351, lng: 103.68 } }),
  ];
  assert.deepEqual(ids(recommendGuestVendors(catalog, { locations: ["Area A"] })), [2, 3, 1]);
});

test("dietary choices never move an area's centre by removing its other vendors", () => {
  const catalog = [
    vendor(1, { halal: false, location: "Area A", map_coordinates: { lat: 1.35, lng: 103.68 } }),
    vendor(2, { halal: true, location: "Nearby A", map_coordinates: { lat: 1.351, lng: 103.68 } }),
  ];
  const result = recommendGuestVendors(catalog, { halal: true, locations: ["Area A"] });
  assert.deepEqual(ids(result), [2]);
  assert.ok(Math.abs(result[0].discovery_distance_m - 111.2) < 1);
});

test("preference options come from the real catalog and exclude duplicate, missing and demo values", () => {
  assert.deepEqual(guestDiscoveryOptions([
    vendor(1), vendor(2), vendor(3, { category: "Cafe", location: "South Spine" }),
    vendor(4, { category: null, location: null }),
    vendor(5, { category: "Demo", location: "Demo Canteen" }),
  ]), { categories: ["Cafe", "Chinese restaurant"], locations: ["North Spine", "South Spine"] });
});

test("GPS alone ranks by user-to-vendor distance without requiring a named area", () => {
  const catalog = [
    vendor(1, { location: "Far away", average_rating: 5, map_coordinates: { lat: 1.36, lng: 103.68 } }),
    vendor(2, { location: "Nearby", map_coordinates: { lat: 1.3501, lng: 103.68 } }),
    vendor(3, { location: "No coordinates" }),
  ];
  const result = recommendGuestVendors(catalog, { userLocation: { lat: 1.35, lng: 103.68 } });
  assert.deepEqual(ids(result), [2, 1, 3]);
  assert.ok(Math.abs(result[0].discovery_distance_m - 11.12) < 0.1);
  assert.equal(result[0].discovery_distance_from, "you");
  assert.equal(result[0].discovery_distance_source, "gps");
  assert.equal(result[2].discovery_distance_m, null);
  assert.equal(result[2].discovery_distance_from, null);
});

test("GPS joins selected areas and each result identifies its actual nearest reference", () => {
  const catalog = [
    vendor(1, { location: "Area A", map_coordinates: { lat: 1.35, lng: 103.68 } }),
    vendor(2, { location: "Near user", map_coordinates: { lat: 1.3601, lng: 103.68 } }),
  ];
  const result = recommendGuestVendors(catalog, {
    locations: ["Area A"], userLocation: { lat: 1.36, lng: 103.68 },
  });
  const areaPick = result.find((item) => item.id === 1);
  const gpsPick = result.find((item) => item.id === 2);
  assert.equal(areaPick.discovery_distance_m, 0);
  assert.equal(areaPick.discovery_distance_from, "Area A");
  assert.equal(areaPick.discovery_distance_source, "area");
  assert.ok(gpsPick.discovery_distance_m < 12);
  assert.equal(gpsPick.discovery_distance_from, "you");
  assert.equal(gpsPick.discovery_distance_source, "gps");
});

test("area fallback names the actual closest selected area when GPS is absent", () => {
  const catalog = [
    vendor(1, { location: "Area A", map_coordinates: { lat: 1.35, lng: 103.68 } }),
    vendor(2, { location: "Area B", map_coordinates: { lat: 1.36, lng: 103.68 } }),
    vendor(3, { location: "Near B", map_coordinates: { lat: 1.3601, lng: 103.68 } }),
  ];
  const pick = recommendGuestVendors(catalog, { locations: ["Area A", "Area B"], userLocation: null })
    .find((item) => item.id === 3);
  assert.equal(pick.discovery_distance_from, "Area B");
  assert.equal(pick.discovery_distance_source, "area");
  assert.ok(pick.discovery_distance_m < 12);
});

test("invalid GPS values fall back to selected areas without NaN distances", () => {
  const catalog = [vendor(1, { location: "Area A", map_coordinates: { lat: 1.35, lng: 103.68 } })];
  for (const userLocation of [{ lat: NaN, lng: 103.68 }, { lat: 91, lng: 0 }, { lat: 0, lng: -181 }, { lat: "1.35", lng: 103.68 }, {}]) {
    const [pick] = recommendGuestVendors(catalog, { locations: ["Area A"], userLocation });
    assert.equal(pick.discovery_distance_m, 0);
    assert.equal(pick.discovery_distance_from, "Area A");
    assert.equal(pick.discovery_distance_source, "area");
    const [withoutArea] = recommendGuestVendors(catalog, { userLocation });
    assert.equal(withoutArea.discovery_distance_m, null);
  }
});

test("zero-valued GPS coordinates are valid and an exact GPS tie is labelled from you", () => {
  const catalog = [vendor(1, { location: "Area A", map_coordinates: { lat: 0, lng: 0 } })];
  const [pick] = recommendGuestVendors(catalog, { locations: ["Area A"], userLocation: { lat: 0, lng: 0 } });
  assert.equal(pick.discovery_distance_m, 0);
  assert.equal(pick.discovery_distance_from, "you");
  assert.equal(pick.discovery_distance_source, "gps");
});

test("GPS proximity preserves food preferences and strict dietary filtering", () => {
  const catalog = [
    vendor(1, { halal: true, vegetarian: true, category: "Cafe", map_coordinates: { lat: 1.35, lng: 103.68 } }),
    vendor(2, { halal: true, vegetarian: true, map_coordinates: { lat: 1.3501, lng: 103.68 } }),
    vendor(3, { halal: false, vegetarian: true, map_coordinates: { lat: 1.35, lng: 103.68 } }),
    vendor(4, { halal: true, vegetarian: false, map_coordinates: { lat: 1.35, lng: 103.68 } }),
  ];
  const result = recommendGuestVendors(catalog, {
    userLocation: { lat: 1.35, lng: 103.68 }, categories: ["Chinese restaurant"], halal: true, vegetarian: true,
  });
  assert.deepEqual(ids(result), [2, 1]);
  assert.ok(result.every((item) => item.discovery_distance_from === "you"));
  assert.deepEqual(ids(catalog), [1, 2, 3, 4]);
});
