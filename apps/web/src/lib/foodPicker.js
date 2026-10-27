import { CITATION_MARKER_PATTERN, citationNumbers } from "../components/citationMarkers.js";

export const FOOD_OPTIONS = [
  { id: "rice", label: "Chicken rice", emoji: "🍚" },
  { id: "noodles", label: "Noodles", emoji: "🍜" },
  { id: "burgers", label: "Burgers", emoji: "🍔" },
  { id: "pasta", label: "Pasta", emoji: "🍝" },
  { id: "biryani", label: "Biryani", emoji: "🍛" },
  { id: "mala", label: "Mala", emoji: "🌶️" },
  { id: "pizza", label: "Pizza", emoji: "🍕" },
  { id: "sushi", label: "Sushi", emoji: "🍣" },
  { id: "prata", label: "Roti prata", emoji: "🫓" },
  { id: "dim-sum", label: "Dim sum", emoji: "🥟" },
  { id: "fish-soup", label: "Fish soup", emoji: "🍲" },
  { id: "bibimbap", label: "Bibimbap", emoji: "🥘" },
  { id: "fried-rice", label: "Fried rice", emoji: "🍳" },
  { id: "laksa", label: "Laksa", emoji: "🍜" },
  { id: "sandwich", label: "Sandwich", emoji: "🥪" },
  { id: "dumpling", label: "Dumpling", emoji: "🥟" },
  { id: "salad", label: "Salad", emoji: "🥗" },
  { id: "poke", label: "Poke bowls", emoji: "🥙" },
  { id: "curry", label: "Curry rice", emoji: "🍛" },
  { id: "bbq", label: "BBQ", emoji: "🍖" },
  { id: "fish-chips", label: "Fish & chips", emoji: "🐟" },
  { id: "satay", label: "Satay", emoji: "🍢" },
  { id: "tacos", label: "Tacos", emoji: "🌮" },
  { id: "hotpot", label: "Hotpot", emoji: "🍲" },
];

/** Rebase on the same visible food, then roll through the entire list to the result. */
export function foodRollTarget(currentChoice, count, random = Math.random) {
  const selectedIndex = Math.floor(random() * count);
  return {
    resetIndex: count + currentChoice,
    targetIndex: count * 4 + selectedIndex,
    selectedIndex,
  };
}

/**
 * The picker receives the directory as candidate evidence. Only cited, linked
 * or explicitly named places have actually been surfaced to the user.
 * @template T
 * @param {string} answer
 * @param {T[]} sources
 * @returns {T[]}
 */
export function pickerRecommendationSources(answer, sources) {
  const cited = new Set([...answer.matchAll(new RegExp(CITATION_MARKER_PATTERN, "g"))]
    .flatMap((match) => citationNumbers(match[1])));
  const linked = new Set([...answer.matchAll(/\/vendors\/(\d+)\b/g)].map((match) => Number(match[1])));
  const normalize = (value) => value.normalize("NFKC").replace(/[’‘]/g, "'").toLowerCase();
  const answerText = normalize(answer);
  return sources.filter((source, index) => {
    if (cited.has(index + 1)) return true;
    if (!source || typeof source !== "object") return false;
    const vendor = /** @type {Record<string, unknown>} */ (source);
    if (linked.has(vendor.vendor_id)) return true;
    if (typeof vendor.vendor_name !== "string" || !vendor.vendor_name.trim()) return false;
    const name = normalize(vendor.vendor_name.trim()).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    return new RegExp(`(?:^|[^\\p{L}\\p{N}])${name}(?=$|[^\\p{L}\\p{N}])`, "u").test(answerText);
  });
}
