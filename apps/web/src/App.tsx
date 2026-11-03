import { useEffect, useState } from "react";
import { Routes, Route, Link } from "react-router-dom";
import Layout, { FoodieChat } from "./components/Layout";
import Footer from "./components/Footer";
import Header from "./components/Header";
import { apiUrl } from "./api/client";
import { fetchReviews, fetchVendorReviews } from "./api/reviews.js";
import { fetchVendors } from "./api/vendors";
import SignInPage from "./pages/SignInPage";
import FoodPage from "./pages/FoodPage";
import GuestDiscoverPage from "./pages/GuestDiscoverPage";
import VendorsPage from "./pages/VendorsPage";
import FoodPreferencesOnboarding from "./components/FoodPreferencesOnboarding";
import { fetchMyPreferences } from "./api/preferences.js";
import { useAuth } from "./contexts/AuthContext";
import { useChat } from "./contexts/ChatContext";
import VendorMap from "./pages/VendorMap";
import MapPage from "./pages/MapPage";
import NotFoundPage from "./pages/NotFoundPage";
import AccountPage from "./pages/AccountPage";
import {
  MapPin,
  ChevronRight,
  Clock,
} from "lucide-react";
import StarRow from "./components/StarRow";
import { cn } from "./lib/cn";
import { rankTrendingVendors } from "./lib/trendingVendors";

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

type TrendingVendor = {
  id: number;
  name: string;
  location: string | null;
  category: string | null;
  cuisine: string | null;
  price_range: string | null;
  image_url: string | null;
  halal: boolean | null;
  vegetarian: boolean | null;
  average_rating: number | null;
  average_google_rating: number | null;
  review_count: number;
  created_at: string;
  topReview: string | null;
};

function HomePage() {
  const { openChat } = useChat();
  const [reviewsPaused, setReviewsPaused] = useState(false);
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

        const ranked = rankTrendingVendors(vendors, 4);

        const withTopReviews = await Promise.all(
          ranked.map(async (vendor) => {
            try {
              const page = await fetchVendorReviews(vendor.id, { limit: 1 });
              return { ...vendor, topReview: page.items[0]?.comment ?? null };
            } catch {
              return { ...vendor, topReview: null };
            }
          })
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

  return (
    <div className="min-h-screen overflow-x-hidden bg-cream text-ink">
      {/* ── NAV ──────────────────────────────────────── */}
      <Header fixed />

      {/* ── HERO ─────────────────────────────────────────────────────────── */}
      <section className="relative overflow-hidden border-b border-line-warm bg-cream pb-12 pt-24 sm:pb-16 lg:pb-20">
        <div className="pointer-events-none absolute inset-0" aria-hidden="true">
          <div className="absolute -left-40 top-10 h-[28rem] w-[28rem] rounded-full bg-rose-200/40 blur-3xl" />
          <div className="absolute -right-40 bottom-0 h-[30rem] w-[30rem] rounded-full bg-brand-bright/10 blur-3xl" />
        </div>

        <div className="page-container relative z-10">
          <div className="grid items-center gap-10 lg:grid-cols-12 lg:gap-12">
            {/* Left: editorial copy */}
            <div className="lg:col-span-6">
              {/* Pill + mascot */}
              <div className="flex flex-wrap items-center gap-3">
                <span className="badge badge-primary">
                  Meet your campus guide
                </span>

                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    onClick={openChat}
                    aria-label="Open Foodie chatbot"
                    title="Ask Foodie"
                    className="group shrink-0 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-primary"
                  >
                    <img
                      src="/ntummy_mascot.svg"
                      alt=""
                      aria-hidden="true"
                      className="h-14 w-14 animate-[mascot-float_2.4s_ease-in-out_infinite] object-contain transition-transform group-hover:scale-105 group-active:scale-95 sm:h-16 sm:w-16"
                    />
                  </button>

                  <span
                    aria-hidden="true"
                    className="relative hidden max-w-[220px] rounded-xl border border-line-warm bg-surface-warm px-3 py-2 text-xs font-medium leading-snug text-ink shadow-lg sm:inline-block"
                  >
                    Hi! I&apos;m Foodie — click me to chat!
                    <span className="absolute -left-1.5 top-1/2 h-3 w-3 -translate-y-1/2 rotate-45 border-b border-l border-line-warm bg-surface-warm" />
                  </span>
                </div>
              </div>

              {/* Speech bubble on narrow screens */}
              <p
                aria-hidden="true"
                className="relative mt-3 inline-block max-w-[240px] rounded-xl border border-line-warm bg-surface-warm px-3 py-2 text-xs font-medium leading-snug text-ink shadow-sm sm:hidden"
              >
                Hi! I&apos;m Foodie — click me to chat!
                <span className="absolute -top-1.5 left-8 h-3 w-3 rotate-45 border-l border-t border-line-warm bg-surface-warm" />
              </p>

              <h1 className="type-display-xl mt-5 sm:mt-6">
                Find your next
                <span className="type-accent mt-1 block">favourite food</span>
              </h1>

              <p className="type-body-lg mt-5 max-w-md text-ink-soft sm:mt-6">
                Discover hidden gems across 13 canteens, cosy cafes, fast food
                outlets and restaurants — rated, reviewed and recommended by
                fellow NTU foodies.
              </p>

              <div className="mt-8">
                <Link
                  to="/discover"
                  className="btn btn-primary btn-lg btn-pill w-full sm:w-auto"
                >
                  Discover Now
                  <ChevronRight className="h-4 w-4" aria-hidden="true" />
                </Link>
              </div>

              <dl className="mt-8 grid max-w-md grid-cols-3 gap-3 border-t border-line-warm pt-6 sm:gap-4">
                {[
                  ["50+", "Food stalls"],
                  ["2,400+", "Reviews"],
                  ["13", "Canteens"],
                ].map(([value, label]) => (
                  <div key={label}>
                    <dt className="type-caption text-ink-muted">{label}</dt>
                    <dd className="type-display mt-0.5 text-xl text-ink sm:text-2xl">
                      {value}
                    </dd>
                  </div>
                ))}
              </dl>
            </div>

            {/* Right: two featured stalls */}
            <div className="lg:col-span-6 lg:col-start-7 lg:row-start-1">
              {trendingLoading ? (
                <div className="flex justify-center gap-3 sm:gap-4">
                  <div className="h-80 w-1/2 animate-pulse rounded-3xl border border-line-warm bg-surface-warm/60" />
                  <div className="h-80 w-1/2 animate-pulse rounded-3xl border border-line-warm bg-surface-warm/60" />
                </div>
              ) : trendingVendors.length === 0 ? (
                <div className="type-body rounded-3xl border border-line-warm bg-surface-warm p-8 text-center text-ink-muted">
                  No stalls available right now.
                </div>
              ) : (
                <div className="flex justify-center gap-3 sm:gap-4">
                  {trendingVendors.slice(0, 2).map((vendor, index) => {
                    const rating =
                      vendor.average_rating ?? vendor.average_google_rating;

                    return (
                      <Link
                        key={vendor.id}
                        to={`/vendors/${vendor.id}`}
                        className={cn(
                          "group flex w-1/2 flex-col rounded-3xl border border-line-warm bg-surface-warm p-3 transition-all duration-300",
                          index === 0
                            ? "-translate-y-3 hover:-translate-y-5"
                            : "translate-y-3 hover:translate-y-1"
                        )}
                      >
                        <div className="relative mb-3 aspect-[3/4] overflow-hidden rounded-2xl bg-amber-100">
                          {vendor.image_url ? (
                            <img
                              src={apiUrl(vendor.image_url)}
                              alt={vendor.name}
                              className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105"
                            />
                          ) : (
                            <div className="type-caption flex h-full items-center justify-center p-2 text-center text-ink-muted">
                              No image available
                            </div>
                          )}
                          <span className="badge badge-rating absolute right-2 top-2">
                            {rating != null ? `${rating.toFixed(1)}★` : "—"}
                          </span>
                        </div>

                        <div className="px-1 pb-1">
                          <div className="flex items-center justify-between gap-1 text-sm font-bold text-ink">
                            <span className="truncate">{vendor.name}</span>
                            <span
                              className="text-primary transition-transform group-hover:translate-x-0.5"
                              aria-hidden="true"
                            >
                              ›
                            </span>
                          </div>
                          <div className="type-caption mt-1 flex items-center gap-1 text-ink-muted">
                            <MapPin className="h-3 w-3 shrink-0 text-primary/70" />
                            <span className="truncate">
                              {vendor.location ?? "NTU Campus"}
                            </span>
                          </div>
                        </div>
                      </Link>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* ── TRENDING STALLS ──────────────────────────────────────────────── */}
      <section className="section border-b border-line-warm bg-brand-bright text-white">
        <div className="page-container">
          <div className="mb-10 flex flex-col justify-between gap-4 md:flex-row md:items-end">
            <div>
              <span className="badge badge-on-brand">This week&apos;s picks</span>
              <h2 className="type-display mt-4 text-white">
                Trending on campus
              </h2>
            </div>
            <Link
              to="/food"
              className="inline-flex items-center gap-1.5 text-sm font-semibold text-amber-200 transition-colors hover:text-white"
            >
              View all stalls
              <ChevronRight className="h-4 w-4" aria-hidden="true" />
            </Link>
          </div>

          {trendingLoading ? (
            <div className="grid gap-8 sm:grid-cols-2">
              {[0, 1, 2, 3].map((i) => (
                <div
                  key={i}
                  className="h-64 animate-pulse rounded-[2rem] border border-white/20 bg-white/10 sm:h-80"
                />
              ))}
            </div>
          ) : trendingVendors.length === 0 ? (
            <div className="rounded-[2rem] border border-white/20 bg-white/10 py-16 text-center text-amber-100/80">
              No stalls to show yet.
            </div>
          ) : (
            <div className="grid gap-8 sm:grid-cols-2">
              {trendingVendors.map((vendor) => {
                const rating =
                  vendor.average_rating ?? vendor.average_google_rating;

                return (
                  <Link
                    key={vendor.id}
                    to={`/vendors/${vendor.id}`}
                    className="group flex cursor-pointer flex-col overflow-hidden rounded-[2rem] border border-line-warm bg-card shadow-xl transition-all duration-300 hover:-translate-y-1.5 hover:border-primary/30"
                  >
                    <div className="relative h-48 overflow-hidden bg-muted">
                      {vendor.image_url ? (
                        <img
                          src={apiUrl(vendor.image_url)}
                          alt={`${vendor.name} dish`}
                          className="h-full w-full object-cover transition-transform duration-700 ease-out group-hover:scale-105"
                        />
                      ) : (
                        <div className="type-caption flex h-full items-center justify-center text-ink-muted">
                          No image available
                        </div>
                      )}
                      <div className="absolute left-3 top-3 flex flex-wrap gap-1.5">
                        {vendor.cuisine && (
                          <span className="badge badge-glass">
                            {vendor.cuisine}
                          </span>
                        )}
                      </div>
                      <span className="badge badge-rating absolute right-3 top-3">
                        {rating != null ? `${rating.toFixed(1)}★` : "—"}
                      </span>
                      {(vendor.halal === true || vendor.vegetarian === true) && (
                        <div className="absolute bottom-3 right-3 flex flex-wrap justify-end gap-1.5">
                          {vendor.halal === true && (
                            <span className="badge badge-glass">Halal</span>
                          )}
                          {vendor.vegetarian === true && (
                            <span className="badge badge-glass">Vegetarian</span>
                          )}
                        </div>
                      )}
                    </div>

                    <div className="flex flex-1 flex-col justify-between bg-card p-5">
                      <div>
                        <h3 className="text-base font-bold leading-snug text-ink transition-colors group-hover:text-primary">
                          {vendor.name}
                        </h3>
                        <div className="type-caption mt-1.5 flex items-center gap-1.5 text-ink-muted">
                          <MapPin className="h-3.5 w-3.5 shrink-0 text-primary/70" />
                          <span className="truncate">
                            {vendor.location ?? "NTU"}
                          </span>
                        </div>
                        <div className="type-caption mt-3 flex items-center justify-between text-ink-muted">
                          <StarRow rating={rating ?? 0} />
                          <span>{vendor.review_count} reviews</span>
                        </div>
                      </div>

                      <div className="mt-auto border-t border-line-warm pt-3.5">
                        {vendor.topReview && (
                          <p className="type-caption mb-3 line-clamp-2 rounded-xl bg-cream p-2 italic leading-relaxed text-ink-muted">
                            &ldquo;{vendor.topReview}&rdquo;
                          </p>
                        )}
                        <div className="flex items-center justify-between">
                          <span className="type-caption font-bold text-ink">
                            {vendor.price_range ?? "Price unlisted"}
                          </span>
                          <span className="type-caption rounded-md bg-cream-deep px-2 py-0.5 text-ink-muted">
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

          <div className="mt-10 flex justify-center">
            <Link to="/food" className="btn btn-inverse btn-lg btn-pill">
              View more
              <ChevronRight className="h-4 w-4" aria-hidden="true" />
            </Link>
          </div>
        </div>
      </section>

      {/* ── REVIEWS ──────────────────────────────────────────────────────── */}
      <section className="section border-b border-line-warm bg-cream-deep">
        <div className="page-container">
          <div className="mb-12">
            <span className="badge badge-primary">From the community</span>
            <h2 className="type-display mt-4 text-ink">
              What students are saying
            </h2>
          </div>

          {reviewsLoading ? (
            <div className="grid gap-6 md:grid-cols-3">
              {[0, 1, 2].map((item) => (
                <div
                  key={item}
                  className="h-64 animate-pulse rounded-[2rem] border border-line-warm bg-card shadow-sm"
                />
              ))}
            </div>
          ) : reviews.length === 0 ? (
            <div className="type-body rounded-[2rem] border border-line-warm bg-card py-16 text-center text-ink-muted shadow-sm">
              No reviews available yet.
            </div>
          ) : (
            <>
              <div
                className="grid gap-6 md:grid-cols-3"
                onMouseEnter={() => setReviewsPaused(true)}
                onMouseLeave={() => setReviewsPaused(false)}
                onFocus={() => setReviewsPaused(true)}
                onBlur={() => setReviewsPaused(false)}
              >
                {reviews
                  .slice(reviewSlide * 3, reviewSlide * 3 + 3)
                  .map((review) => (
                    <Link
                      key={review.id}
                      to={`/vendors/${review.vendor.id}`}
                      className="group flex cursor-pointer flex-col rounded-[2rem] border border-line-warm bg-card p-6 shadow-md transition-all duration-300 hover:border-primary/40 hover:shadow-2xl md:p-8"
                    >
                      <div className="mb-5 flex items-center justify-between">
                        <div className="flex min-w-0 items-center gap-3">
                          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary/15 text-sm font-extrabold text-primary shadow-sm">
                            {review.user.display_name.charAt(0).toUpperCase()}
                          </div>
                          <div className="min-w-0">
                            <div className="truncate text-sm font-bold text-ink transition-colors group-hover:text-primary">
                              {review.user.display_name}
                            </div>
                            <div className="type-caption truncate text-ink-muted">
                              {review.user.affiliation || "NTU"}
                            </div>
                          </div>
                        </div>
                        <div className="type-caption flex shrink-0 items-center gap-1 rounded-full bg-muted/60 px-2 py-1 text-ink-muted">
                          <Clock className="h-3 w-3" aria-hidden="true" />
                          {new Date(review.created_at).toLocaleDateString()}
                        </div>
                      </div>

                      <div className="mb-4 flex items-center gap-2 rounded-xl border border-line-warm bg-cream p-2.5">
                        <StarRow rating={review.rating} />
                        <span className="type-caption text-ink-muted">at</span>
                        <span className="type-caption truncate font-bold text-primary">
                          {review.vendor.name}
                        </span>
                      </div>

                      <p className="type-body mb-6 flex-1 text-ink-soft">
                        &ldquo;{review.comment || ""}&rdquo;
                      </p>

                      <div className="type-caption flex items-center justify-between border-t border-line-warm pt-4 text-ink-muted">
                        <div className="flex items-center gap-1.5 font-medium">
                          <MapPin className="h-3.5 w-3.5 text-primary/70" />
                          {review.vendor.location || "NTU"}
                        </div>
                      </div>
                    </Link>
                  ))}
              </div>

              {reviewSlideCount > 1 && (
                <div className="mt-10 flex justify-center gap-2">
                  {Array.from({ length: reviewSlideCount }).map((_, index) => (
                    <button
                      key={index}
                      type="button"
                      onClick={() => setReviewSlide(index)}
                      aria-label={`Go to review slide ${index + 1}`}
                      aria-current={reviewSlide === index}
                      className={cn(
                        "h-2.5 cursor-pointer rounded-full transition-all duration-300",
                        reviewSlide === index
                          ? "w-8 bg-primary"
                          : "w-2.5 bg-ink/20 hover:bg-ink/40"
                      )}
                    />
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </section>

      {/* ── CAMPUS MAP TEASER ────────────────────────────────────────────── */}
      <section className="section border-b border-line-warm bg-cream-deep">
        <div className="page-container">
          <div className="rounded-[2.5rem] border border-line-warm bg-card/90 p-8 shadow-2xl shadow-amber-900/5 backdrop-blur-md md:p-12">
            <div className="mx-auto mb-10 max-w-xl text-center">
              <span className="badge badge-primary">Navigate campus</span>
              <h2 className="type-display mt-4 text-ink">
                All food places in one map
              </h2>
              <p className="type-body mt-3 text-ink-soft">
                Check what&apos;s available nearby and plan your campus food
                route in seconds.
              </p>
            </div>

            <div className="overflow-hidden rounded-2xl border border-line-warm bg-muted/30 shadow-inner">
              <VendorMap />
            </div>
          </div>
        </div>
      </section>

      {/* ── SIGN-UP CTA ──────────────────────────────────────────────────── */}
      <section className="relative overflow-hidden border-b border-line-warm bg-brand-bright text-white">
        <div className="grid min-h-[420px] items-stretch md:grid-cols-12">
          {/* Left: mascot */}
          <div className="relative flex min-h-[380px] items-center justify-start overflow-hidden border-r border-line-warm bg-gradient-to-br from-rose-50 via-rose-100 to-cream p-8 pl-6 sm:pl-12 md:col-span-6 md:min-h-full md:pl-16">
            <div
              className="pointer-events-none absolute inset-0 flex items-center justify-center"
              aria-hidden="true"
            >
              <div className="h-72 w-72 rounded-full bg-rose-300/50 blur-3xl" />
            </div>

            <button
              type="button"
              onClick={openChat}
              className="group relative flex w-full max-w-sm cursor-pointer flex-col items-center justify-center pt-6 text-left focus-visible:outline-none"
              aria-label="Open Foodie Chatbot"
            >
              <span className="relative z-20 mb-2 block max-w-[250px] rounded-2xl border border-line-warm bg-card px-4 py-4 text-xs font-medium leading-snug text-ink shadow-xl transition-transform duration-300 group-hover:-translate-y-0.5 sm:text-sm">
                Too many food options? Sign up and I&apos;ll recommend the one
                just for you!
                <span
                  className="absolute -bottom-1.5 left-6 h-4 w-4 rotate-45 border-b border-r border-line-warm bg-card"
                  aria-hidden="true"
                />
              </span>

              <img
                src="/ntummy_mascot_uncertain.png"
                alt=""
                className="z-10 mt-4 h-auto w-52 object-contain drop-shadow-xl transition-transform duration-500 group-hover:scale-105 group-active:scale-95 sm:w-64"
              />
            </button>
          </div>

          {/* Centre logo badge */}
          <div className="pointer-events-none absolute left-1/2 top-1/2 z-20 hidden -translate-x-1/2 -translate-y-1/2 md:flex">
            <div className="flex h-24 w-24 items-center justify-center rounded-full border border-white/20 bg-white p-3 shadow-2xl lg:h-28 lg:w-28">
              <img
                src="/ntummy_logo.svg"
                alt="NTUmmy logo"
                className="h-full w-full object-contain"
              />
            </div>
          </div>

          {/* Right: copy + CTA */}
          <div className="relative z-10 flex flex-col justify-center bg-brand-bright p-8 sm:p-12 lg:p-16 md:col-span-6">
            <h2 className="type-display text-white">
              Still unsure of
              <br />
              what to eat?
            </h2>

            <p className="type-body mt-4 max-w-md text-amber-100/90">
              Create a NTUmmy account for personalised food recommendations
              based on your preferences and dietary needs.
            </p>

            <div className="mt-8">
              <Link to="/signin" className="btn btn-inverse btn-lg btn-pill">
                Sign up
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* ── FOOTER ───────────────────────────────────────────────────────── */}
      <Footer />
    </div>
  );
}

function App() {
  const { session, loading } = useAuth();
  
  const userId = session?.user?.id ?? null;

  const [preferenceStatus, setPreferenceStatus] = useState<
    "pending" | "completed" | "skipped" | null
  >(null);

  const [preferenceLoadError, setPreferenceLoadError] = useState(false);
  const [preferenceRetry, setPreferenceRetry] = useState(0);

  useEffect(() => {
    let active = true;

    async function loadPreferences() {
      if (loading) return;

      if (!userId) {
        setPreferenceStatus(null);
        return;
      }

      try {
        setPreferenceLoadError(false);

        const preferences = await fetchMyPreferences();

        if (!active) return;

        if (!preferences) {
          setPreferenceStatus("pending");
          return;
        }

        if (
          preferences.onboarding_status === "completed" ||
          preferences.onboarding_status === "skipped"
        ) {
          setPreferenceStatus(preferences.onboarding_status);
        } else {
          setPreferenceStatus("pending");
        }
      } catch (error) {
        console.error("Unable to load food preferences", error);

        if (!active) return;

        setPreferenceLoadError(true);
      }
    }

    void loadPreferences();

    return () => {
      active = false;
    };
  }, [userId, loading, preferenceRetry]);

  return (
    <>
      <Routes>
        <Route path="/" element={<HomePage />} />

        <Route
          element={
            <Layout
              preferenceStatus={preferenceStatus}
              openPreferences={() => setPreferenceStatus("pending")}
            />
          }
        >
          <Route path="/food" element={<FoodPage />} />
          <Route path="/discover" element={<GuestDiscoverPage />} />
          <Route path="/map" element={<MapPage />} />
          <Route path="/vendors/:vendorId" element={<VendorsPage />} />
          <Route path="/account" element={<AccountPage />} />
          <Route path="signin" element={<SignInPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>

      <FoodieChat />

      {preferenceLoadError && (
        <div className="fixed bottom-6 right-6 z-[110] w-[min(92vw,380px)] rounded-2xl border border-border bg-card p-5 shadow-2xl backdrop-blur-md">
          <p className="text-sm font-bold text-ink">
            Unable to load food preferences
          </p>

          <p className="mt-1 text-xs text-ink-muted">
            You can retry loading your preferences or close this message.
          </p>

          <div className="mt-4 flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setPreferenceLoadError(false)}
              className="btn btn-ghost btn-sm"
            >
              Close
            </button>

            <button
              type="button"
              onClick={() => {
                setPreferenceLoadError(false);
                setPreferenceRetry((current) => current + 1);
              }}
              className="btn btn-primary btn-sm"
            >
              Retry
            </button>
          </div>
        </div>
      )}

      {session && preferenceStatus === "pending" && (
        <FoodPreferencesOnboarding
          onFinished={(status) => setPreferenceStatus(status)}
        />
      )}
    </>
  );
}

export default App;