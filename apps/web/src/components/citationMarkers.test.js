import assert from "node:assert/strict";
import test from "node:test";

import { CITATION_MARKER_PATTERN, citationNumbers } from "./citationMarkers.js";

test("citation marker pattern recognizes single and grouped source numbers", () => {
  const matcher = new RegExp(CITATION_MARKER_PATTERN, "g");
  const answer = "Internal reviews [1, 2, 3, 8] and another source [7].";

  const matches = [...answer.matchAll(matcher)];

  assert.deepEqual(matches.map((match) => match[0]), ["[1, 2, 3, 8]", "[7]"]);
  assert.deepEqual(citationNumbers(matches[0][1]), [1, 2, 3, 8]);
  assert.deepEqual(citationNumbers(matches[1][1]), [7]);
});

test("citation marker pattern leaves ordinary bracketed text alone", () => {
  const matcher = new RegExp(CITATION_MARKER_PATTERN, "g");

  assert.equal("[internal reviews]".match(matcher), null);
  assert.equal("[1 and 2]".match(matcher), null);
});
