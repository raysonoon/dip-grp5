// Friendly price bands shown in the UI, mapped to the price_range strings the
// API stores. The stored values come from the Google/directory CSVs and are
// either Google-style ($, $$, ...) or range-style ($1-10, $10-20, $20-30).
export const PRICE_BANDS = [
  { label: "Under $10", values: ["$", "$1-10"] },
  { label: "$10–20", values: ["$$", "$10-20"] },
  { label: "Over $20", values: ["$$$", "$$$$", "$20-30"] },
];

// Labels are used directly as select values so the UI shows friendly text.
export const PRICE_BAND_OPTIONS = PRICE_BANDS.map((band) => band.label);

// Expand selected band labels into the raw price_range values to filter on.
export function priceRangeValues(labels = []) {
  return PRICE_BANDS.filter((band) => labels.includes(band.label)).flatMap(
    (band) => band.values,
  );
}
