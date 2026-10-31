import assert from "node:assert/strict";
import test from "node:test";

import { SITE_TITLE, formatDocumentTitle } from "./documentTitle.js";

test("page titles use the '<Page name> | NTU Food Guide' format", () => {
  assert.equal(SITE_TITLE, "NTU Food Guide");
  assert.equal(formatDocumentTitle("Map"), "Map | NTU Food Guide");
  assert.equal(formatDocumentTitle("  Koufu Stall  "), "Koufu Stall | NTU Food Guide");
});

test("missing or blank names fall back to the site title", () => {
  for (const name of [undefined, null, "", "   "]) {
    assert.equal(formatDocumentTitle(name), "NTU Food Guide");
  }
});
