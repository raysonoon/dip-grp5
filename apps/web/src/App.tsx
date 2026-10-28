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
import VendorsPage from "./pages/VendorsPage";
import FoodPreferencesOnboarding from "./components/FoodPreferencesOnboarding";
import { fetchMyPreferences } from "./api/preferences.js";
import { useAuth } from "./contexts/AuthContext";
import VendorMap from "./pages/VendorMap";
import MapPage from "./pages/MapPage";
import NotFoundPage from "./pages/NotFoundPage";
import AccountPage from "./pages/AccountPage";
import {
  Star,
  MapPin,
  ChevronRight,
  Clock,
} from "lucide-react";
import { rankTrendingVendors } from "./lib/trendingVendors";

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

function StarRow({
  rating,
  size = "sm",
}: {
  rating: number;
  size?: "sm" | "md";
}) {
  return (
    <div className="flex items-center gap-0.5">
      {[1, 2, 3, 4, 5].map((i) => (
        <Star
          key={i}
          className={`${size === "sm" ? "w-3.5 h-3.5" : "w-4 h-4"} ${
            i <= Math.round(rating)
              ? "fill-amber-500 text-amber-500"
              : "fill-transparent text-amber-200/50"
          }`}
        />
      ))}
    </div>
  );
}

function HomePage() {
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
    <div
      className="min-h-screen bg-[#FAF6F0] text-[#5C4033] overflow-x-hidden"
      style={{ fontFamily: BODY_FONT }}
    >
      {/* ── NAV ──────────────────────────────────────── */}
      <Header fixed />

      {/* ── HERO SECTION WITH ROSE GRADIENT CARD, EDITORIAL FRAMES & MASCOT ── */}
      <section className="relative min-h-[85vh] flex items-center py-16 bg-[#FAF6F0] overflow-hidden border-b border-amber-900/10">
        {/* Soft background ambient glow highlights */}
        <div className="absolute top-10 left-[-5%] w-96 h-96 bg-rose-200/40 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute bottom-[-10%] right-[-5%] w-[450px] h-[450px] bg-rose-300/30 rounded-full blur-3xl pointer-events-none" />

        <div className="relative z-10 max-w-[1400px] mx-auto px-6 py-8 w-full">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-center">
            
            {/* Left Column (5 Cols): Main Hero Card Container with Rose-Dominant Warm Pastel Gradient */}
            <div className="lg:col-span-5 bg-gradient-to-br from-rose-200/90 via-pink-100/80 to-amber-100/80 backdrop-blur-md p-8 sm:p-10 rounded-[2.5rem] border border-rose-300/40 shadow-xl shadow-rose-900/10">
              <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full border border-rose-500/25 bg-rose-500/10 text-rose-800 text-xs font-semibold mb-6 tracking-wide shadow-sm">
                BUILT BY STUDENTS, FOR STUDENTS
              </div>

              <h1 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold font-display leading-[1.1] mb-6 tracking-tight text-[#4A3328]">
                Find Your Next
                <span className="block text-rose-700 italic font-normal mt-1">
                  Favourite Stall
                </span>
              </h1>

              <p className="text-sm sm:text-base text-[#6E5548] mb-8 leading-relaxed font-normal">
                Discover hidden gems across 13 canteens, cozy cafes, fast food
                outlets and restaurants — rated, reviewed, and recommended by your
                fellow NTU foodies.
              </p>

              {/* Stats Section */}
              <div className="grid grid-cols-3 gap-4 sm:gap-6 pt-6 border-t border-rose-900/15">
                {[
                  ["50+", "Food Stalls"],
                  ["2,400+", "Reviews"],
                  ["13", "Canteens"],
                ].map(([num, label]) => (
                  <div key={label} className="space-y-0.5">
                    <div className="text-2xl sm:text-3xl font-extrabold text-[#4A3328] font-display tracking-tight">
                      {num}
                    </div>
                    <div className="text-[11px] font-medium text-[#7D6355] uppercase tracking-wider">
                      {label}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Center Column (4 Cols): Two Offset Editorial Frames */}
            <div className="lg:col-span-4 flex items-center justify-center gap-4 sm:gap-5 py-4">
              
              {/* Frame 1: Pasta Express (Slightly Higher) */}
              <div className="w-1/2 sm:w-60 bg-[#FFFDF9] rounded-3xl p-3 border border-[#E8DCD0] shadow-[6px_6px_0px_0px_rgba(203,137,126,0.35)] -translate-y-4 transform hover:-translate-y-6 hover:shadow-[8px_8px_0px_0px_rgba(203,137,126,0.45)] transition-all duration-300">
                <div className="relative h-56 sm:h-64 rounded-2xl overflow-hidden mb-3 bg-amber-100">
                  <img
                    src="/data/vendor_photos/downloads/V002_1.jpg"
                    alt="Pasta Express"
                    className="w-full h-full object-cover"
                    onError={(e) => {
                      e.currentTarget.src = "https://images.unsplash.com/photo-1551183053-bf91a1d81141?auto=format&fit=crop&w=800&q=80";
                    }}
                  />
                </div>
                <div className="px-2 pb-1">
                  <div className="flex items-center justify-between text-xs font-bold text-[#4A3328] mb-1">
                    <span>Pasta Express</span>
                    <span className="text-[#B22222]">›</span>
                  </div>
                  <div className="flex items-center gap-1 text-[11px] text-[#7D6355]">
                    <MapPin className="w-3 h-3 text-amber-800 flex-shrink-0" />
                    <span className="truncate">North Spine</span>
                  </div>
                </div>
              </div>

              {/* Frame 2: The Crowded Bowl (Slightly Lower) */}
              <div className="w-1/2 sm:w-50 bg-[#FFFDF9] rounded-3xl p-2.5 border border-[#E8DCD0] shadow-[6px_6px_0px_0px_rgba(203,137,126,0.35)] translate-y-4 transform hover:translate-y-2 hover:shadow-[8px_8px_0px_0px_rgba(203,137,126,0.45)] transition-all duration-300">
                <div className="relative h-44 sm:h-52 rounded-2xl overflow-hidden mb-3 bg-amber-100">
                  <img
                    src="/data/vendor_photos/downloads/V002_2.jpg"
                    alt="The Crowded Bowl"
                    className="w-full h-full object-cover"
                    onError={(e) => {
                      e.currentTarget.src = "https://images.unsplash.com/photo-1546069901-ba9599a7e63c?auto=format&fit=crop&w=600&q=80";
                    }}
                  />
                </div>
                <div className="px-2 pb-1">
                  <div className="flex items-center justify-between text-xs font-bold text-[#4A3328] mb-1">
                    <span className="truncate">The Crowded Bowl</span>
                    <span className="text-[#B22222]">›</span>
                  </div>
                  <div className="flex items-center gap-1 text-[11px] text-[#7D6355]">
                    <MapPin className="w-3 h-3 text-amber-800 flex-shrink-0" />
                    <span className="truncate">North Spine</span>
                  </div>
                </div>
              </div>

            </div>

            {/* Right Column (3 Cols): NTUmmy Mascot Right of Editorial Frames */}
            <div className="lg:col-span-3 flex justify-center lg:justify-end items-center">
              <img
                src="/ntummy_mascot.svg"
                alt="NTUmmy Mascot"
                className="w-56 sm:w-64 lg:w-72 h-auto object-contain pointer-events-none drop-shadow-[0_20px_30px_rgba(74,51,40,0.12)] transform hover:scale-105 transition-transform duration-500 ease-out"
              />
            </div>

          </div>
        </div>
      </section>

      {/* ── CAMPUS MAP TEASER ── */}
      <section className="relative py-20 bg-[#F5EFE6] overflow-hidden border-b border-amber-900/10">
        <div className="relative z-10 max-w-7xl mx-auto px-6">
          <div className="bg-white/90 backdrop-blur-md rounded-[2.5rem] border border-amber-900/10 p-8 md:p-12 shadow-2xl shadow-amber-900/5 transition-all duration-300">
            <div className="text-center max-w-xl mx-auto mb-10">
              <span className="inline-block px-3 py-1 rounded-full bg-primary/10 text-primary text-xs font-bold uppercase tracking-widest mb-3">
                Navigate Campus
              </span>
              <h2 className="text-3xl md:text-4xl font-extrabold mb-3 font-display tracking-tight text-[#4A3328]">
                All Food Places in 1 Map
              </h2>
              <p className="text-[#6E5548] text-sm md:text-base leading-relaxed">
                Check what's available nearby and plan your campus food route in seconds.
              </p>
            </div>

            <div className="rounded-2xl overflow-hidden border border-border shadow-inner bg-muted/30">
              <VendorMap />
            </div>
          </div>
        </div>
      </section>

      {/* ── TRENDING STALLS (Dark Red Background #f0404b) ──── */}
      <section className="relative py-20 bg-[#f0404b] text-white border-b border-amber-900/10 overflow-hidden">
        <div className="relative z-10 max-w-7xl mx-auto px-6">
          <div className="flex flex-col md:flex-row md:items-end justify-between mb-10 gap-4">
            <div>
              <span className="inline-block px-3.5 py-1 rounded-full bg-amber-500/20 text-amber-200 text-xs font-bold uppercase tracking-widest mb-3 border border-amber-400/20">
                This Week's Picks
              </span>
              <h2 className="text-3xl md:text-4xl font-extrabold font-display tracking-tight text-white">
                Trending on Campus
              </h2>
            </div>
            <Link
              to="/food"
              className="inline-flex items-center gap-1.5 text-sm font-semibold text-amber-200 hover:text-white transition-colors group"
            >
              View all stalls{" "}
              <ChevronRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
            </Link>
          </div>

          {trendingLoading ? (
            <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-6">
              {[0, 1, 2, 3].map((i) => (
                <div
                  key={i}
                  className="h-80 rounded-[2rem] bg-white/10 border border-white/20 animate-pulse shadow-sm"
                />
              ))}
            </div>
          ) : trendingVendors.length === 0 ? (
            <div className="text-center py-16 bg-white/10 rounded-[2rem] border border-white/20 text-amber-100/80 shadow-sm">
              No stalls to show yet.
            </div>
          ) : (
            <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-6">
              {trendingVendors.map((vendor) => {
                const rating =
                  vendor.average_rating ?? vendor.average_google_rating;
                return (
                  <Link
                    key={vendor.id}
                    to={`/vendors/${vendor.id}`}
                    className="group rounded-[2rem] border border-amber-900/10 bg-white overflow-hidden hover:border-amber-300 hover:-translate-y-1.5 transition-all duration-300 shadow-xl flex flex-col cursor-pointer"
                  >
                    <div className="relative h-48 overflow-hidden bg-muted">
                      {vendor.image_url ? (
                        <img
                          src={apiUrl(vendor.image_url)}
                          alt={`${vendor.name} dish`}
                          className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-700 ease-out"
                        />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center text-xs text-[#7D6355] font-medium">
                          No image available
                        </div>
                      )}
                      <div className="absolute top-3 left-3 flex gap-1.5 flex-wrap">
                        {vendor.category && (
                          <span
                            key={vendor.category}
                            className="px-2.5 py-1 rounded-full text-[11px] font-semibold bg-white/90 text-[#5C4033] border border-amber-900/10 backdrop-blur-md shadow-sm"
                          >
                            {vendor.category}
                          </span>
                        )}
                      </div>
                      <div className="absolute top-3 right-3 px-2.5 py-1 rounded-xl bg-[#B22222] text-white text-xs font-bold shadow-md">
                        {rating != null ? `${rating.toFixed(1)}★` : "—"}
                      </div>
                    </div>

                    <div className="p-5 flex flex-col flex-1 justify-between bg-white">
                      <div>
                        <h3 className="font-bold text-base leading-snug mb-1.5 text-[#4A3328] group-hover:text-rose-700 transition-colors">
                          {vendor.name}
                        </h3>
                        <div className="flex items-center gap-1.5 text-xs text-[#7D6355] mb-3">
                          <MapPin className="w-3.5 h-3.5 flex-shrink-0 text-amber-800" />
                          <span className="truncate">
                            {vendor.location ?? "NTU"}
                          </span>
                        </div>
                        <div className="flex items-center justify-between text-xs text-[#7D6355] mb-4">
                          <StarRow rating={rating ?? 0} />
                          <span className="font-medium">
                            {vendor.review_count} reviews
                          </span>
                        </div>
                      </div>

                      <div className="border-t border-amber-900/10 pt-3.5 mt-auto">
                        {vendor.topReview && (
                          <p className="text-xs text-[#7D6355] italic leading-relaxed line-clamp-2 mb-3 bg-[#FAF6F0] p-2 rounded-xl">
                            &ldquo;{vendor.topReview}&rdquo;
                          </p>
                        )}
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-bold text-[#4A3328]">
                            {vendor.price_range ?? "Price unlisted"}
                          </span>
                          <span className="text-xs font-medium text-[#7D6355] bg-amber-100/50 px-2 py-0.5 rounded-md">
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

      {/* ── REVIEWS ──────────────────── */}
      <section className="relative py-20 bg-[#F5EFE6] overflow-hidden border-b border-amber-900/10">
        <div className="relative z-10 max-w-7xl mx-auto px-6">
          <div className="flex items-end justify-between mb-12">
            <div>
              <span className="inline-block px-3.5 py-1 rounded-full bg-orange-500/15 text-orange-900 text-xs font-bold uppercase tracking-widest mb-3">
                From the Community
              </span>
              <h2 className="text-3xl md:text-4xl font-extrabold font-display tracking-tight text-[#4A3328]">
                What students are saying
              </h2>
            </div>
          </div>

          {reviewsLoading ? (
            <div className="grid md:grid-cols-3 gap-6">
              {[0, 1, 2].map((item) => (
                <div
                  key={item}
                  className="p-6 rounded-[2rem] border border-amber-900/10 bg-white animate-pulse h-64 shadow-sm"
                />
              ))}
            </div>
          ) : reviews.length === 0 ? (
            <div className="text-center py-16 text-[#7D6355] bg-white rounded-[2rem] border border-amber-900/10 shadow-sm">
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
                      className="p-6 md:p-8 rounded-[2rem] border border-amber-900/10 bg-white flex flex-col hover:border-rose-400 hover:shadow-2xl hover:shadow-amber-900/10 transition-all duration-300 group cursor-pointer shadow-md"
                    >
                      <div className="flex items-center justify-between mb-5">
                        <div className="flex items-center gap-3 min-w-0">
                          <div className="w-10 h-10 rounded-full bg-primary/15 flex items-center justify-center text-primary text-sm font-extrabold flex-shrink-0 shadow-sm">
                            {review.user.display_name.charAt(0).toUpperCase()}
                          </div>
                          <div className="min-w-0">
                            <div className="text-sm font-bold truncate text-[#4A3328] group-hover:text-primary transition-colors">
                              {review.user.display_name}
                            </div>
                            <div className="text-xs text-[#7D6355] truncate font-medium">
                              {review.user.affiliation || "NTU"}
                            </div>
                          </div>
                        </div>
                        <div className="flex items-center gap-1 text-[11px] font-medium text-[#7D6355] flex-shrink-0 bg-muted/60 px-2 py-1 rounded-full">
                          <Clock className="w-3 h-3 text-[#7D6355]" />
                          {new Date(review.created_at).toLocaleDateString()}
                        </div>
                      </div>

                      <div className="flex items-center gap-2 mb-4 bg-amber-50/70 p-2.5 rounded-xl border border-amber-900/5">
                        <StarRow rating={review.rating} />
                        <span className="text-xs text-[#7D6355] font-medium">
                          at
                        </span>
                        <span className="text-xs font-bold text-primary truncate">
                          {review.vendor.name}
                        </span>
                      </div>

                      <p className="text-sm text-[#6E5548] leading-relaxed flex-1 mb-6 font-normal">
                        &ldquo;{review.comment || ""}&rdquo;
                      </p>

                      <div className="flex items-center justify-between text-xs text-[#7D6355] border-t border-amber-900/10 pt-4">
                        <div className="flex items-center gap-1.5 font-medium">
                          <MapPin className="w-3.5 h-3.5 text-primary/70" />
                          {review.vendor.location || "NTU"}
                        </div>
                      </div>
                    </Link>
                  ))}
              </div>

              <div className="flex justify-center gap-2 mt-10">
                {Array.from({ length: reviewSlideCount }).map((_, index) => (
                  <button
                    key={index}
                    type="button"
                    onClick={() => setReviewSlide(index)}
                    aria-label={`Go to review slide ${index + 1}`}
                    className={`h-2.5 rounded-full transition-all duration-300 ${
                      reviewSlide === index
                        ? "w-8 bg-primary"
                        : "w-2.5 bg-amber-900/20 hover:bg-amber-900/40"
                    }`}
                  />
                ))}
              </div>
            </>
          )}
        </div>
      </section>

      {/* ── STILL UNSURE OF WHAT TO EAT? (Dark Red Section Background #f0404b) ── */}
      <section className="relative bg-[#f0404b] overflow-hidden text-white border-b border-amber-900/10">
        <div className="grid md:grid-cols-12 items-stretch min-h-[420px]">
          
          {/* Left Side: White Text & Button Container */}
          <div className="md:col-span-6 p-8 sm:p-12 lg:p-16 flex flex-col justify-center relative z-10 bg-[#f0404b]">
            
            <h2 className="text-4xl sm:text-5xl lg:text-6xl font-serif text-white font-normal leading-tight mb-4">
              Still Unsure of <br />
              What to Eat?
            </h2>
            
            <p className="text-xs sm:text-sm lg:text-base text-amber-100/90 font-light mb-8 whitespace-nowrap overflow-hidden text-ellipsis">
              Chat with Foodie for personalised food recommendations in NTU.
            </p>

            <div>
              <button
                type="button"
                onClick={() => {
                  window.dispatchEvent(new CustomEvent("open-foodie-chat"));
                }}
                className="inline-flex items-center gap-2.5 px-8 py-3.5 rounded-full bg-white text-[#B22222] font-semibold text-sm shadow-lg hover:bg-amber-50 hover:scale-105 active:scale-95 transition-all duration-300 cursor-pointer"
              >
                <div className="w-6 h-6 rounded-full bg-[#B22222]/10 flex items-center justify-center p-0.5 flex-shrink-0">
                  <img
                    src="/ntummy_mascot_head.svg"
                    alt="NTUmmy Mascot"
                    className="w-full h-full object-contain"
                  />
                </div>
                <span>Foodie</span>
              </button>
             </div>
            </div>

          {/* Center Floating NTUmmy Logo Badge */}
          <div className="hidden md:flex absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 z-20 pointer-events-none">
            <div className="w-24 h-24 lg:w-28 lg:h-28 rounded-full bg-white p-3 shadow-2xl border border-white/20 flex items-center justify-center transform hover:scale-105 transition-transform">
              <img
                src="/ntummy_logo.svg"
                alt="NTUmmy Logo"
                className="w-full h-full object-contain"
              />
            </div>
          </div>

          {/* Right Side: NTUmmy mascot */}
          <div className="md:col-span-6 relative min-h-[380px] md:min-h-full bg-gradient-to-br from-[#fff8f2] via-[#fde8e2] to-[#faf6f0] flex items-center justify-end pr-6 sm:pr-12 md:pr-16 p-8 overflow-hidden border-l border-amber-900/10">
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
    <div className="w-72 h-72 bg-rose-300/60 rounded-full blur-3xl" />
  </div>

  {/* Centered Container */}
  <div className="relative max-w-sm w-full flex flex-col items-center justify-center pt-6">
    
    {/* Speech Bubble: Positioned above-left of mascot head with downward pointing tail */}
    <div className="absolute top-2 -left-12 sm:-left-20 lg:-left-40 z-25 bg-white text-[#4A3328] px-4 py-5 rounded-2xl shadow-xl border border-amber-900/10 max-w-[220px] sm:max-w-[250px] text-xs sm:text-sm font-medium leading-snug">
      <p>Hi! I'm Foodie, your campus food guide! Ask me anything about campus food.</p>
      
      {/* Speech bubble tail pointing downwards towards Foodie's head */}
      <div className="absolute -bottom-2 right-6 w-4 h-4 bg-white border-r border-b border-amber-900/10 transform rotate-45" />
    </div>

    {/* Mascot Image: Centered */}
    <img
      src="/ntummy_mascot.svg"
      alt="Foodie Mascot"
      className="w-52 sm:w-64 h-auto object-contain drop-shadow-xl z-10 mt-6"
    />
  </div>
 </div>

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
          <Route path="/map" element={<MapPage />} />
          <Route path="/vendors/:vendorId" element={<VendorsPage />} />
          <Route path="/account" element={<AccountPage />} />
          <Route path="signin" element={<SignInPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>

      {preferenceLoadError && (
        <div className="fixed bottom-6 right-6 z-[110] w-[min(92vw,380px)] rounded-2xl border border-border bg-card p-5 shadow-2xl backdrop-blur-md">
          <p className="text-sm font-bold text-[#4A3328]">
            Unable to load food preferences
          </p>

          <p className="mt-1 text-xs text-[#7D6355]">
            You can retry loading your preferences or close this message.
          </p>

          <div className="mt-4 flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setPreferenceLoadError(false)}
              className="rounded-xl px-3 py-2 text-xs font-semibold text-[#7D6355] hover:text-[#4A3328] transition-colors"
            >
              Close
            </button>

            <button
              type="button"
              onClick={() => {
                setPreferenceLoadError(false);
                setPreferenceRetry((current) => current + 1);
              }}
              className="rounded-xl bg-primary px-4 py-2 text-xs font-bold text-primary-foreground hover:opacity-95 shadow-md transition-opacity"
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