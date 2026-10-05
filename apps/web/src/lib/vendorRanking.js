// Ranking helpers for the /map page. Distance itself comes from PostGIS
// (distance_m on each vendor); this module only blends it with the rating.

export function vendorRating(vendor) {
  return vendor.average_rating ?? vendor.average_google_rating ?? null;
}

export function formatDistance(meters) {
  if (meters == null || !Number.isFinite(meters)) return "";
  if (meters < 1000) return `${Math.round(meters)} m`;
  return `${(meters / 1000).toFixed(1)} km`;
}

// distanceWeight is 0..1: 1 ranks purely by closeness, 0 purely by rating.
export function rankVendors(vendors, { maxDistanceM, distanceWeight }) {
  const weight = Math.min(1, Math.max(0, distanceWeight));
  const range = Math.max(maxDistanceM, 1);

  return vendors
    .map((vendor) => {
      const rating = vendorRating(vendor);
      const distanceScore =
        vendor.distance_m == null ? 0 : 1 - Math.min(vendor.distance_m / range, 1);
      const ratingScore = rating == null ? 0 : rating / 5;
      return {
        ...vendor,
        score: weight * distanceScore + (1 - weight) * ratingScore,
      };
    })
    .sort(
      (a, b) =>
        b.score - a.score ||
        (a.distance_m ?? Infinity) - (b.distance_m ?? Infinity) ||
        a.name.localeCompare(b.name),
    );
}

// Used when there is no location: best rated first, unrated last.
export function sortByRating(vendors) {
  return [...vendors].sort(
    (a, b) =>
      (vendorRating(b) ?? -1) - (vendorRating(a) ?? -1) || a.name.localeCompare(b.name),
  );
}