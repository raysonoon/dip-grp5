import assert from "node:assert/strict";
import test from "node:test";

import { containsVendorName, vendorNameMentions } from "./vendorNameLinks.js";

test("a new catalog name links using the id supplied by its sources, with case and whitespace tolerance", () => {
  const text = "Try **MAPLE   Kitchen (East)** or Maple Kitchen (East).";
  const mentions = vendorNameMentions(text, [
    { vendor_id: 831, vendor_name: "Maple Kitchen (East)" },
    { vendor_id: 831, vendor_name: "MAPLE\nKitchen (East)" },
  ]);
  assert.equal(mentions.length, 2);
  for (const mention of mentions) {
    assert.equal(mention.vendorId, 831);
    assert.equal(text.slice(mention.start, mention.end), mention.text);
  }
  assert.equal(text.slice(mentions[0].start - 2, mentions[0].start), "**");
  assert.equal(text.slice(mentions[0].end, mentions[0].end + 2), "**");
});

test("the same normalized name with distinct vendor ids stays plain instead of choosing a branch", () => {
  const mentions = vendorNameMentions("Try Maple Kitchen.", [
    { vendor_id: 831, vendor_name: "Maple Kitchen" },
    { vendor_id: 920, vendor_name: " maple\nKITCHEN " },
  ]);
  assert.deepEqual(mentions.map(({ text, vendorId }) => ({ text, vendorId })), [
    { text: "Maple Kitchen", vendorId: null },
  ]);
});

test("ambiguous longer names also prevent a shorter vendor from linking inside them", () => {
  const mentions = vendorNameMentions("Tea Cafe and Tea", [
    { vendor_id: 10, vendor_name: "Tea" },
    { vendor_id: 11, vendor_name: "Tea Cafe" },
    { vendor_id: 12, vendor_name: "TEA CAFE" },
  ]);
  assert.deepEqual(mentions.map(({ text, vendorId }) => ({ text, vendorId })), [
    { text: "Tea Cafe", vendorId: null },
    { text: "Tea", vendorId: 10 },
  ]);
});

test("no target is guessed from missing, malformed, or unsafe vendor ids", () => {
  const invalid = [null, {}, { vendor_id: "8", vendor_name: "Maple" },
    { vendor_id: 0, vendor_name: "Maple" }, { vendor_id: -1, vendor_name: "Maple" },
    { vendor_id: Number.MAX_SAFE_INTEGER + 1, vendor_name: "Maple" },
    { vendor_id: 8, vendor_name: 123 }, { vendor_id: 8, vendor_name: "  " }];
  assert.deepEqual(vendorNameMentions("Maple is here.", invalid), []);
});

test("longest complete names win and ordinary words containing a vendor name remain unchanged", () => {
  assert.deepEqual(vendorNameMentions("Teapot, Tea Cafe (North), then Tea.", [
    { vendor_id: 1, vendor_name: "  Tea                               " },
    { vendor_id: 2, vendor_name: "Tea Cafe (North)" },
  ]).map(({ text, vendorId }) => ({ text, vendorId })), [
    { text: "Tea Cafe (North)", vendorId: 2 },
    { text: "Tea", vendorId: 1 },
  ]);
});

test("unusual Unicode case matches cannot manufacture a missing source identity", () => {
  // Unicode regex case folding recognizes long-s as S. If name identity cannot
  // be established with the same normalized source key, leave the text plain.
  assert.deepEqual(vendorNameMentions("The ſhop is open.", [
    { vendor_id: 1, vendor_name: "Shop" },
  ]).map(({ text, vendorId }) => ({ text, vendorId })), [
    { text: "ſhop", vendorId: null },
  ]);
});

test("canonical names containing regex punctuation are treated as literal source data", () => {
  assert.deepEqual(vendorNameMentions("Visit A+B [Cafe] (West).", [
    { vendor_id: 42, vendor_name: "A+B [Cafe] (West)" },
  ]).map(({ text, vendorId }) => ({ text, vendorId })), [
    { text: "A+B [Cafe] (West)", vendorId: 42 },
  ]);
});

test("citation name detection uses the same case, whitespace, and word boundaries", () => {
  assert.equal(containsVendorName("Try MAPLE\u00a0 Kitchen today [1].", "Maple Kitchen"), true);
  assert.equal(containsVendorName("Try Teapot today [1].", "Tea"), false);
  assert.equal(containsVendorName("Unknown place [1].", "  "), false);
});

test("complete source names link when adjacent to Chinese prose and punctuation", () => {
  const mentions = vendorNameMentions("推荐去Quad Cafe (SBS)，也可以试Maple Kitchen。GELÁRE也不错。", [
    { vendor_id: 9, vendor_name: "Quad Cafe (SBS)" },
    { vendor_id: 831, vendor_name: "Maple Kitchen" },
    { vendor_id: 55, vendor_name: "Geláre" },
  ]);
  assert.deepEqual(mentions.map(({ text, vendorId }) => ({ text, vendorId })), [
    { text: "Quad Cafe (SBS)", vendorId: 9 },
    { text: "Maple Kitchen", vendorId: 831 },
    { text: "GELÁRE", vendorId: 55 },
  ]);
  assert.equal(containsVendorName("推荐去Quad Cafe (SBS)，那里不错。", "Quad Cafe (SBS)"), true);
});

test("mixed-script support does not link a source name embedded in a longer Latin word", () => {
  const sources = [{ vendor_id: 9, vendor_name: "Quad Cafe (SBS)" }];
  assert.deepEqual(vendorNameMentions("SuperQuad Cafe (SBS) or Quad Cafe (SBS)Bonus", sources), []);
  assert.equal(containsVendorName("SuperQuad Cafe (SBS)", "Quad Cafe (SBS)"), false);
});

test("mixed-script prose keeps ambiguous same-name branches plain", () => {
  const mentions = vendorNameMentions("推荐去MAPLE   Kitchen，那里不错。", [
    { vendor_id: 831, vendor_name: "Maple Kitchen" },
    { vendor_id: 920, vendor_name: "MAPLE KITCHEN" },
  ]);
  assert.deepEqual(mentions.map(({ text, vendorId }) => ({ text, vendorId })), [
    { text: "MAPLE   Kitchen", vendorId: null },
  ]);
});
