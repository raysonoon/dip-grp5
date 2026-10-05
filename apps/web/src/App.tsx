import { useEffect, useState, type FormEvent } from "react";
import { Routes, Route, Link, useNavigate } from "react-router-dom";
import Layout, { FoodieChat } from "./components/Layout";
import Footer from "./components/Footer";
import Header from "./components/Header";
import { apiUrl } from "./api/client";
import { fetchReviews, fetchVendorReviews } from "./api/reviews.js";
import { fetchVendors } from "./api/vendors";
import SignInPage from "./pages/SignInPage";
import FoodPage from "./pages/FoodPage";
import VendorsPage from "./pages/VendorsPage";
import VendorMap from "./pages/VendorMap";
import {
  Search,
  Star,
  MapPin,
  ChevronRight,
  Clock,
  TrendingUp,
  //ThumbsUp,//
} from "lucide-react";

const BODY_FONT = "'Plus Jakarta Sans', sans-serif";

type Review = {
  id: number;
  rating: number;
  comment: string | null;
  created_at: string;
  user: {
    id: number;
    display_name: string;
    affiliation: string | null;
  };
  vendor: {
    id: number;
    name: string;
    location: string | null;
  };
};

const TRENDING_WEIGHTS = {
  recency: 0.4,
  reviews: 0.35,
  rating: 0.25,
};

type TrendingVendor = {
  id: number;
  name: string;
  location: string | null;
  category: string | null;
  price_range: string | null;
  image_url: string | null;
  average_rating: number | null;
  average_google_rating: number | null;
  review_count: number;
  created_at: string;
  topReview: string | null;
};

function computeTrendingScore(
  vendor: {
    created_at: string;
    review_count: number;
    average_rating: number | null;
    average_google_rating: number | null;
  },
  maxReviewCount: number,
  minCreatedAt: number,
  maxCreatedAt: number,
) {
  const created = new Date(vendor.created_at).getTime();
  const recency = (created - minCreatedAt) / Math.max(maxCreatedAt - minCreatedAt, 1);
  const reviews = maxReviewCount > 0 ? vendor.review_count / maxReviewCount : 0;
  const rating = vendor.average_rating ?? vendor.average_google_rating ?? 0;
  const ratingScore = Math.min(1, rating / 5);
  return (
    TRENDING_WEIGHTS.recency * recency +
    TRENDING_WEIGHTS.reviews * reviews +
    TRENDING_WEIGHTS.rating * ratingScore
  );
}

function StarRow({ rating, size = "sm" }: { rating: number; size?: "sm" | "md" }) {
  return (
    <div className="flex items-center gap-0.5">
      {[1, 2, 3, 4, 5].map((i) => (
        <Star
          key={i}
          className={`${size === "sm" ? "w-3.5 h-3.5" : "w-4 h-4"} ${
            i <= Math.round(rating)
              ? "fill-primary text-primary"
              : "fill-transparent text-muted"
          }`}
        />
      ))}
    </div>
  );
}

function HomePage() {
  const [reviewsPaused, setReviewsPaused] = useState(false);
  const navigate = useNavigate();
  const [searchQuery, setSearchQuery] = useState("");
  const [reviews, setReviews] = useState<Review[]>([]);
  const [reviewsLoading, setReviewsLoading] = useState(true);
  const [reviewSlide, setReviewSlide] = useState(0);
  const reviewSlideCount = Math.ceil(reviews.length / 3);

  useEffect(() => {
    const controller = new AbortController();
  
    async function loadReviews() {
      try {
        const response = await fetchReviews(15, 0, controller.signal);
        setReviews(response.items);
      } catch (error) {
        if (!controller.signal.aborted) {
          console.error("Failed to fetch reviews:", error);
        }
      } finally {
        if (!controller.signal.aborted) {
          setReviewsLoading(false);
        }
      }
    }
  
    loadReviews();
  
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (reviewSlideCount <= 1 || reviewsPaused) return;
  
    const interval = window.setInterval(() => {
      setReviewSlide((current) => (current + 1) % reviewSlideCount);
    }, 8000);
  
    return () => window.clearInterval(interval);
  }, [reviewSlideCount, reviewsPaused]);

  useEffect(() => {
    if (reviewSlideCount > 0 && reviewSlide >= reviewSlideCount) {
      setReviewSlide(0);
    }
  }, [reviewSlide, reviewSlideCount]);

  const [trendingVendors, setTrendingVendors] = useState<TrendingVendor[]>([]);
  const [trendingLoading, setTrendingLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    setTrendingLoading(true);

    fetchVendors("", controller.signal)
      .then(async (vendors: TrendingVendor[]) => {
        if (vendors.length === 0) {
          setTrendingVendors([]);
          return;
        }

        const createdTimes = vendors.map((vendor) =>
          new Date(vendor.created_at).getTime(),
        );
        const minCreatedAt = Math.min(...createdTimes);
        const maxCreatedAt = Math.max(...createdTimes);
        const maxReviewCount = Math.max(
          ...vendors.map((vendor) => vendor.review_count),
        );

        const ranked = vendors
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
          .slice(0, 4)
          .map((entry) => entry.vendor);

        const withTopReviews = await Promise.all(
          ranked.map(async (vendor) => {
            try {
              // Only the first review's comment is used, so one review is enough.
              const page = await fetchVendorReviews(vendor.id, {
                limit: 1,
                signal: controller.signal,
              });
              return { ...vendor, topReview: page.items[0]?.comment ?? null };
            } catch {
              return { ...vendor, topReview: null };
            }
          }),
        );

        setTrendingVendors(withTopReviews);
      })
      .catch(() => {
        setTrendingVendors([]);
      })
      .finally(() => {
        if (!controller.signal.aborted) setTrendingLoading(false);
      });

    return () => controller.abort();
  }, []);

  function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const query = searchQuery.trim();
    if (!query) return;
    navigate(`/food?q=${encodeURIComponent(query)}`);
  }

  return (
    <div
      className="min-h-screen bg-background text-foreground overflow-x-hidden"
      style={{ fontFamily: BODY_FONT }}
    >
      {/* ── NAV ──────────────────────────────────────── */}
      <Header fixed />

      {/* ── HERO ─────────────────────────────────────── */}
      <section className="relative min-h-screen flex items-center pt-16">
        <div
          className="absolute inset-0 bg-cover bg-center bg-no-repeat bg-muted"
          style={{
            backgroundImage:
              "url('https://images.unsplash.com/photo-1628532429788-c35922b5e6c1?w=1600&h=900&fit=crop&auto=format')",
          }}
        />
        <div className="absolute inset-0 bg-gradient-to-r from-background/96 via-background/84 to-background/20" />
        <div className="absolute inset-0 bg-gradient-to-t from-background/50 via-transparent to-transparent" />

        <div className="relative z-10 max-w-7xl mx-auto px-6 py-28">
          <div className="max-w-2xl">
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-primary/30 bg-primary/10 text-primary text-xs font-semibold mb-7 tracking-wide">
              BUILT BY STUDENTS, FOR STUDENTS <TrendingUp className="w-3.5 h-3.5" />
            </div>

            <h1
              className="text-5xl md:text-6xl lg:text-7xl font-bold leading-[1.05] mb-6 font-display"
            >
              Find Your Next
              <span className="block text-primary italic">Favourite Stall</span>
            </h1>

            <p className="text-lg text-muted-foreground mb-8 leading-relaxed">
              Discover hidden gems across 13 canteens, a variety of cafes, fast food outlets and restaurants — rated, reviewed, and recommended by your fellow NTU foodies.
            </p>

            {/* Search bar */}
            <form className="flex gap-3 mb-7" onSubmit={submitSearch}>
              <div className="flex-1 flex items-center gap-3 px-4 py-3 rounded-xl bg-card border border-border focus-within:border-primary/40 transition-colors">
                <Search className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search for stalls, dishes, canteens..."
                  className="bg-transparent text-sm text-foreground placeholder:text-muted-foreground outline-none flex-1"
              />
              </div>
              <button
                type="submit"
                className="px-5 py-3 rounded-xl bg-primary text-primary-foreground font-semibold text-sm hover:opacity-90 transition-opacity"
              >
                Search
              </button>
            </form>

            {/* Quick tags */}
            <div className="flex flex-wrap gap-2 mb-10">
              {[
                "🍗 Chicken Rice",
                "🍜 Ban Mian",
                "🌶️ Mala",
                "🍱 Bento",
                "🥘 Economy Rice",
                "🍣 Japanese",
              ].map((tag) => (
                <button
                  key={tag}
                  className="px-3 py-1.5 rounded-full text-xs border border-border text-muted-foreground hover:border-primary/40 hover:text-foreground transition-all duration-200"
                >
                  {tag}
                </button>
              ))}
            </div>

            {/* Stats */}
            <div className="flex gap-10">
              {[
                ["50+", "Food Stalls"],
                ["2,400+", "Reviews"],
                ["13", "Canteens"],
              ].map(([num, label]) => (
                <div key={label}>
                  <div
                    className="text-3xl font-bold text-foreground font-display"
                  >
                    {num}
                  </div>
                  <div className="text-xs text-muted-foreground mt-0.5">
                    {label}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ── CAMPUS MAP TEASER ────────────────────────── */}
      <section className="py-24 bg-card border-t border-border">
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center mb-12">
            <p className="text-[#1B2D4F] text-xs font-bold uppercase tracking-widest mb-2">
              Navigate Campus
            </p>
            <h2
              className="text-3xl md:text-4xl font-bold mb-4 font-display"
            >
              All Food Places in 1 Map
            </h2>
            <p className="text-muted-foreground max-w-sm mx-auto text-sm leading-relaxed">
              Check what's available and plan your route in seconds.
            </p>
          </div>

          <VendorMap />
        </div>
      </section>

      {/* ── TRENDING STALLS ───────────────────────────── */}
      <section className="py-24">
        <div className="max-w-7xl mx-auto px-6">
          <div className="flex items-end justify-between mb-12">
            <div>
              <p className="text-primary text-xs font-bold uppercase tracking-widest mb-2">
                This Week's Picks
              </p>
              <h2
                className="text-3xl md:text-4xl font-bold font-display"
              >
                Trending on Campus
              </h2>
            </div>
            <Link
              to="/food"
              className="hidden md:flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              View all stalls <ChevronRight className="w-4 h-4" />
            </Link>
          </div>

          {trendingLoading ? (
            <p className="text-sm text-muted-foreground">Loading trending stalls...</p>
          ) : trendingVendors.length === 0 ? (
            <p className="text-sm text-muted-foreground">No stalls to show yet.</p>
          ) : (
            <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
              {trendingVendors.map((vendor) => {
                const rating = vendor.average_rating ?? vendor.average_google_rating;
                return (
                  <Link
                    key={vendor.id}
                    to={`/vendors/${vendor.id}`}
                    className="group rounded-2xl border border-border bg-card overflow-hidden hover:border-primary/25 transition-all duration-300 cursor-pointer flex flex-col"
                  >
                    <div className="relative h-44 overflow-hidden bg-muted">
                      {vendor.image_url ? (
                        <img
                          src={apiUrl(vendor.image_url)}
                          alt={`${vendor.name} dish`}
                          className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                        />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center text-sm text-muted-foreground">
                          No image
                        </div>
                      )}
                      <div className="absolute top-3 left-3 flex gap-1.5 flex-wrap">
                        {vendor.category && (
                          <span
                            key={vendor.category}
                            className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-background/75 text-foreground border border-border/60 backdrop-blur-sm"
                          >
                            {vendor.category}
                          </span>
                        )}
                      </div>
                      <div className="absolute top-3 right-3 px-2 py-1 rounded-lg bg-primary text-primary-foreground text-xs font-bold">
                        {rating != null ? `${rating.toFixed(1)}★` : "—"}
                      </div>
                    </div>

                    <div className="p-4 flex flex-col flex-1">
                      <h3 className="font-semibold text-sm leading-snug mb-1">
                        {vendor.name}
                      </h3>
                      <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-3">
                        <MapPin className="w-3 h-3 flex-shrink-0" />
                        {vendor.location ?? "NTU"}
                      </div>
                      <div className="flex items-center justify-between text-xs text-muted-foreground mb-3">
                        <StarRow rating={rating ?? 0} />
                        <span>{vendor.review_count} reviews</span>
                      </div>
                      <div className="mt-auto border-t border-border pt-3">
                        {vendor.topReview && (
                          <p className="text-xs text-muted-foreground leading-relaxed line-clamp-2 mb-3">
                            &ldquo;{vendor.topReview}&rdquo;
                          </p>
                        )}
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-bold text-foreground">
                            {vendor.price_range ?? "Price unavailable"}
                          </span>
                          <span className="text-xs text-muted-foreground">
                            {vendor.category ?? "Food"}
                          </span>
                        </div>
                      </div>
                    </div>
                  </Link>
                );
              })}
            </div>
          )}
        </div>
      </section>

      {/* ── REVIEWS ──────────────────────────────────── */}
      <section className="py-24 bg-card border-y border-border">
  <div className="max-w-7xl mx-auto px-6">
    <div className="flex items-end justify-between mb-12">
      <div>
        <p className="text-[#1B2D4F] text-xs font-bold uppercase tracking-widest mb-2">
          From the Community
        </p>
        <h2
          className="text-3xl md:text-4xl font-bold font-display"
        >
          What students are saying
        </h2>
      </div>
    </div>

    {reviewsLoading ? (
      <div className="grid md:grid-cols-3 gap-6">
        {[0, 1, 2].map((item) => (
          <div
            key={item}
            className="p-6 rounded-2xl border border-border bg-background animate-pulse"
          >
            <div className="h-10 w-40 bg-muted rounded mb-5" />
            <div className="h-4 w-32 bg-muted rounded mb-3" />
            <div className="h-20 bg-muted rounded" />
          </div>
        ))}
      </div>
    ) : reviews.length === 0 ? (
      <div className="text-center py-12 text-muted-foreground">
        No reviews available yet.
      </div>
    ) : (
      <>
        <div
          className="grid md:grid-cols-3 gap-6"
          onMouseEnter={() => setReviewsPaused(true)}
          onMouseLeave={() => setReviewsPaused(false)}
        >
          {reviews
            .slice(reviewSlide * 3, reviewSlide * 3 + 3)
            .map((review) => (
              <Link
                key={review.id}
                to={`/vendors/${review.vendor.id}`}
                className="p-6 rounded-2xl border border-border bg-background flex flex-col hover:border-primary/40 transition-colors"
              >
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="w-9 h-9 rounded-full bg-primary/20 flex items-center justify-center text-primary text-sm font-bold flex-shrink-0">
                      {review.user.display_name.charAt(0).toUpperCase()}
                    </div>

                    <div className="min-w-0">
                      <div className="text-sm font-semibold truncate">
                        {review.user.display_name}
                      </div>
                      <div className="text-xs text-muted-foreground truncate">
                        {review.user.affiliation || "NTU"}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-1 text-xs text-muted-foreground flex-shrink-0">
                    <Clock className="w-3 h-3" />
                    {new Date(review.created_at).toLocaleDateString()}
                  </div>
                </div>

                <div className="flex items-center gap-2 mb-3">
                  <StarRow rating={review.rating} />

                  <span className="text-xs text-muted-foreground">
                    at
                  </span>

                  <span className="text-xs font-semibold text-primary truncate">
                    {review.vendor.name}
                  </span>
                </div>

                <p className="text-sm text-muted-foreground leading-relaxed flex-1 mb-4">
                  &ldquo;{review.comment || ""}&rdquo;
                </p>

                <div className="flex items-center text-xs text-muted-foreground border-t border-border pt-3">
                  <div className="flex items-center gap-1.5">
                    <MapPin className="w-3 h-3" />
                    {review.vendor.location || "NTU"}
                  </div>
                </div>
              </Link>
            ))}
        </div>

        <div className="flex justify-center gap-2 mt-8">
        {Array.from({ length: reviewSlideCount }).map((_, index) => (
         <button
           key={index}
           type="button"
           onClick={() => setReviewSlide(index)}
           aria-label={`Go to review slide ${index + 1}`}
           className={`w-2.5 h-2.5 rounded-full transition-colors ${
             reviewSlide === index
               ? "bg-primary"
               : "bg-muted-foreground/30 hover:bg-muted-foreground/50"
             }`}
            />
         ))}
        </div>
      </>
    )}
  </div>
</section>

      {/* ── FLOATING CHATBOT WIDGET ───────────────────── */}
      <FoodieChat />

      {/* ── FOOTER ───────────────────────────────────── */}
      <Footer />
    </div>
  );
}

function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route element={<Layout />}>
        <Route path="/food" element={<FoodPage />} />
        <Route path="/vendors/:vendorId" element={<VendorsPage />} />
        <Route path="signin" element={<SignInPage />} />
      </Route>
    </Routes>
  );
}

export default App;
