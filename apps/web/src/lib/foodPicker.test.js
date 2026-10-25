import assert from "node:assert/strict";
import test from "node:test";
import { FOOD_OPTIONS, foodRollTarget, pickerRecommendationSources } from "./foodPicker.js";

test("every food type participates and can land in the selected row", () => {
  const count = FOOD_OPTIONS.length;
  assert.equal(new Set(FOOD_OPTIONS.map((food) => food.id)).size, count);
  const eligible = new Set();
  for (let index = 0; index < count; index += 1) {
    const roll = foodRollTarget(0, count, () => (index + 0.5) / count);
    eligible.add(FOOD_OPTIONS[roll.selectedIndex].id);
    assert.equal(roll.targetIndex % count, index);
  }
  assert.equal(eligible.size, count);
  assert.equal(foodRollTarget(0, count, () => 0).selectedIndex, 0);
  assert.equal(foodRollTarget(0, count, () => 1 - Number.EPSILON).selectedIndex, count - 1);
});

test("repeated rolls rebase on the previous result and still travel through full lists", () => {
  const count = FOOD_OPTIONS.length;
  for (let previous = 0; previous < count; previous += 1) {
    for (let selected = 0; selected < count; selected += 1) {
      const roll = foodRollTarget(previous, count, () => (selected + 0.5) / count);
      assert.equal(roll.resetIndex % count, previous);
      assert.equal(roll.targetIndex % count, selected);
      assert.ok(roll.targetIndex - roll.resetIndex > count * 2);
      assert.ok(roll.targetIndex + 2 < count * 6);
    }
  }
});

test("only vendors actually cited by picker recommendations are offered to the wheel", () => {
  const sources = [
    { source_type: "vendor", vendor_id: 10 },
    { source_type: "google_review", vendor_id: 20 },
    { source_type: "vendor", vendor_id: 30 },
    { source_type: "reddit", vendor_id: 40 },
  ];
  assert.deepEqual(pickerRecommendationSources("Try these places [2, 4]. Also [2] and [99].", sources), [sources[1], sources[3]]);
  assert.equal(sources.length, 4);
});

test("no-match and retry replies do not fill the wheel with the candidate directory", () => {
  const sources = [{ source_type: "vendor", vendor_id: 10 }];
  assert.deepEqual(pickerRecommendationSources("No confirmed campus match yet.", sources), []);
  assert.deepEqual(pickerRecommendationSources("Please try again.", sources), []);
});

test("named and directly linked picker recommendations qualify without numbered citations", () => {
  const sources = [
    { vendor_id: 82, vendor_name: "Paik's Bibim" },
    { vendor_id: 99, vendor_name: "Other place" },
    { vendor_id: 90, vendor_name: "A much longer name" },
  ];
  assert.deepEqual(pickerRecommendationSources("Try **Paik’s Bibim** and [this place](/vendors/90).", sources), [sources[0], sources[2]]);
  assert.deepEqual(pickerRecommendationSources("Another place nearby.", [{ vendor_id: 2, vendor_name: "Other" }]), []);
});
