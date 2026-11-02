const WORD_CHARACTER = "[\\p{L}\\p{N}_]";
// Chinese prose commonly touches a Latin vendor name without spaces. Han
// characters form a script boundary; Latin letters still cannot extend a name.
const NAME_START = `(?:(?<!${WORD_CHARACTER})|(?<=\\p{Script=Han}))`;
const NAME_END = `(?:(?!${WORD_CHARACTER})|(?=\\p{Script=Han}))`;

/** Use the same identity for names repeated across SQL and review sources. */
export function normalizeVendorName(value) {
  return typeof value === "string" ? value.trim().replace(/\s+/gu, " ").toLowerCase() : "";
}

function namePattern(name) {
  const words = name.trim().split(/\s+/u).map((word) => word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  return `${NAME_START}${words.join("\\s+")}${NAME_END}`;
}

/** Match an official name while tolerating display whitespace and letter case. */
export function containsVendorName(text, name) {
  if (typeof text !== "string" || !normalizeVendorName(name)) return false;
  return new RegExp(namePattern(name), "iu").test(text);
}

/**
 * Find canonical names using only supplied source records. Ambiguous names are
 * returned with no link target so a shorter name cannot link part of them.
 *
 * @param {string} text
 * @param {unknown[]} sources
 * @returns {Array<{ start: number, end: number, text: string, vendorId: number | null }>}
 */
export function vendorNameMentions(text, sources) {
  if (typeof text !== "string" || !Array.isArray(sources)) return [];
  const names = new Map();
  for (const value of sources) {
    if (!value || typeof value !== "object") continue;
    const source = /** @type {{ vendor_id?: unknown, vendor_name?: unknown }} */ (value);
    if (typeof source.vendor_id !== "number" || !Number.isSafeInteger(source.vendor_id) || source.vendor_id <= 0) continue;
    const key = normalizeVendorName(source.vendor_name);
    if (!key) continue;
    const name = /** @type {string} */ (source.vendor_name);
    const entry = names.get(key) ?? { name: name.trim().replace(/\s+/gu, " "), ids: new Set() };
    entry.ids.add(source.vendor_id);
    names.set(key, entry);
  }
  if (names.size === 0) return [];
  const patterns = [...names.values()].sort((left, right) => right.name.length - left.name.length).map((entry) => namePattern(entry.name));
  const matcher = new RegExp(patterns.join("|"), "giu");
  return [...text.matchAll(matcher)].map((match) => {
    const entry = names.get(normalizeVendorName(match[0]));
    return {
      start: match.index,
      end: match.index + match[0].length,
      text: match[0],
      vendorId: entry?.ids.size === 1 ? entry.ids.values().next().value : null,
    };
  });
}
