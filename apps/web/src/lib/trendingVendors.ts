export const TRENDING_WEIGHTS = {
  recency: 0.4,
  reviews: 0.35,
  rating: 0.25,
};

export type TrendingVendorLike = {
  created_at: string;
  review_count: number;
  average_rating: number | null;
  average_google_rating: number | null;
};

export function computeTrendingScore(
  vendor: TrendingVendorLike,
  maxReviewCount: number,
  minCreatedAt: number,
  maxCreatedAt: number,
) {
  const created = new Date(vendor.created_at).getTime();

  const recency =
    (created - minCreatedAt) /
    Math.max(maxCreatedAt - minCreatedAt, 1);

  const reviews =
    maxReviewCount > 0
      ? vendor.review_count / maxReviewCount
      : 0;

  const rating =
    vendor.average_rating ??
    vendor.average_google_rating ??
    0;

  const ratingScore = Math.min(1, rating / 5);

  return (
    TRENDING_WEIGHTS.recency * recency +
    TRENDING_WEIGHTS.reviews * reviews +
    TRENDING_WEIGHTS.rating * ratingScore
  );
}

export function rankTrendingVendors<T extends TrendingVendorLike>(
  vendors: T[],
  limit = 4,
) {
  if (vendors.length === 0) {
    return [];
  }

  const createdTimes = vendors.map((vendor) =>
    new Date(vendor.created_at).getTime(),
  );

  const minCreatedAt = Math.min(...createdTimes);
  const maxCreatedAt = Math.max(...createdTimes);

  const maxReviewCount = Math.max(
    ...vendors.map((vendor) => vendor.review_count),
  );

  return vendors
    .map((vendor) => ({
      vendor,
      score: computeTrendingScore(
        vendor,
        maxReviewCount,
        minCreatedAt,
        maxCreatedAt,
      ),
    }))
    .sort((a, b) => b.score - a.score)
    .slice(0, limit)
    .map((entry) => entry.vendor);
}