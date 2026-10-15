import assert from "node:assert/strict";
import test from "node:test";
import { FOOD_OPTIONS, foodRollTarget } from "./foodPicker.js";

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
