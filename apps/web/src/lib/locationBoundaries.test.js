import test from "node:test";
import assert from "node:assert/strict";
import { buildLocationBoundaries, convexHull, vendorLatLng } from "./locationBoundaries.js";

const v = (id, location, lat, lng) => ({ id, location, map_coordinates: { lat, lng } });

test("vendorLatLng reads {lat,lng} and GeoJSON", () => {
  assert.deepEqual(vendorLatLng({ map_coordinates: { lat: 1, lng: 2 } }), { lat: 1, lng: 2 });
  assert.deepEqual(vendorLatLng({ map_coordinates: { type: "Point", coordinates: [103.6, 1.3] } }), { lat: 1.3, lng: 103.6 });
  assert.equal(vendorLatLng({}), null);
  assert.equal(vendorLatLng({ map_coordinates: { lat: null, lng: null } }), null);
});

test("convexHull drops interior points", () => {
  const pts = [
    { lat: 0, lng: 0 }, { lat: 0, lng: 2 }, { lat: 2, lng: 2 }, { lat: 2, lng: 0 }, { lat: 1, lng: 1 },
  ];
  assert.equal(convexHull(pts).length, 4);
});

test("one boundary per location, with distinct colours", () => {
  const out = buildLocationBoundaries([
    v(1, "North Spine", 1.3480, 103.6800),
    v(2, "North Spine", 1.3482, 103.6804),
    v(3, "The Arc", 1.3440, 103.6780),
    v(4, "Hall 9", null, null),
  ]);
  assert.deepEqual(out.map((b) => b.location), ["North Spine", "The Arc"]);
  assert.notEqual(out[0].color, out[1].color);
  assert.equal(out[0].count, 2);
  assert.ok(out[1].positions.length >= 3); // single vendor still gets an area
});

test("vendors without a location or coordinates are ignored", () => {
  assert.deepEqual(buildLocationBoundaries([{ id: 1, location: "", map_coordinates: { lat: 1, lng: 1 } }]), []);
});