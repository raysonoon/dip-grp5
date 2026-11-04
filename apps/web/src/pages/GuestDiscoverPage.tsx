import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, ArrowRight, DollarSign, Leaf, MapPin, RotateCw, SlidersHorizontal, Sparkles, Star, Store, Utensils } from "lucide-react";
import { apiUrl } from "../api/client";
import { fetchVendors, type parseVendor } from "../api/vendors";
import { guestDiscoveryOptions, recommendGuestVendors } from "../lib/guestDiscovery.js";
import { PRICE_BAND_OPTIONS, priceRangeValues } from "../lib/priceRange.js";
import MultiSelect from "../components/MultiSelect";
import { formatDistance } from "../lib/vendorRanking.js";
import { useDocumentTitle } from "../hooks/useDocumentTitle";
import VendorWheel from "../components/VendorWheel";
import { createWheelSession, visibleResultsForWheel, wheelSessionReducer, type WheelSession } from "../lib/vendorWheel.js";
import { useChat } from "../contexts/ChatContext";

type Vendor = ReturnType<typeof parseVendor>;
type Recommendation = Vendor & {
  discovery_distance_m: number | null;
  discovery_distance_from: string | null;
  discovery_cuisine_match: boolean;
  discovery_category_match: boolean;
  discovery_location_match: boolean;
};
const PAGE_SIZE = 12;

function StarRow({ rating }: { rating: number }) {
  return (
    <div className="flex items-center gap-0.5">
      {[1, 2, 3, 4, 5].map((i) => {
        const fill = Math.max(0, Math.min(1, rating - (i - 1)));
        return (
          <span key={i} className="relative inline-block">
            <Star className="h-3.5 w-3.5 fill-transparent text-muted" />
            <span
              className="absolute inset-0 overflow-hidden"
              style={{ width: `${fill * 100}%` }}
              aria-hidden="true"
            >
              <Star className="h-3.5 w-3.5 fill-primary text-primary" />
            </span>
          </span>
        );
      })}
    </div>
  );
}

export default function GuestDiscoverPage() {
  useDocumentTitle("Discover");
  const { openChat } = useChat();
  const [vendors, setVendors] = useState<Vendor[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [cuisines, setCuisines] = useState<string[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [locations, setLocations] = useState<string[]>([]);
  const [userLocation, setUserLocation] = useState<{ lat: number; lng: number } | null>(null);
  const [geoStatus, setGeoStatus] = useState<"idle" | "requesting" | "granted" | "denied" | "unavailable">("idle");
  const [halal, setHalal] = useState(false);
  const [vegetarian, setVegetarian] = useState(false);
  const [priceBands, setPriceBands] = useState<string[]>([]);
  const [showResults, setShowResults] = useState(false);
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const [wheelSession, setWheelSession] = useState<WheelSession | null>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const locationRequestRef = useRef(0);

  useEffect(() => () => { locationRequestRef.current += 1; }, []);

  function requestLocation() {
    const requestId = ++locationRequestRef.current;
    setUserLocation(null);
    if (!navigator.geolocation) {
      setGeoStatus("unavailable");
      return;
    }
    setGeoStatus("requesting");
    try {
      navigator.geolocation.getCurrentPosition(
        (position) => {
          if (requestId !== locationRequestRef.current) return;
          const point = { lat: position.coords.latitude, lng: position.coords.longitude };
          if (!Number.isFinite(point.lat) || !Number.isFinite(point.lng) || Math.abs(point.lat) > 90 || Math.abs(point.lng) > 180) {
            setGeoStatus("unavailable");
            return;
          }
          setUserLocation(point);
          setGeoStatus("granted");
        },
        (cause) => {
          if (requestId === locationRequestRef.current) setGeoStatus(cause.code === 1 ? "denied" : "unavailable");
        },
        { enableHighAccuracy: false, timeout: 10000, maximumAge: 60000 },
      );
    } catch {
      setGeoStatus("unavailable");
    }
  }

  function clearLocation() {
    locationRequestRef.current += 1;
    setUserLocation(null);
    setGeoStatus("idle");
  }

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    fetchVendors("", controller.signal, { auth: false })
      .then((catalog) => { if (!controller.signal.aborted) setVendors(catalog); })
      .catch((cause) => {
        if (!controller.signal.aborted) {
          setError(cause instanceof Error ? cause.message : "Please try again.");
        }
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [attempt]);

  useEffect(() => {
    headingRef.current?.focus({ preventScroll: true });
    window.scrollTo({ top: 0 });
  }, [showResults]);

  const options = guestDiscoveryOptions(vendors);
  const recommendations: Recommendation[] = recommendGuestVendors(vendors, { cuisines, categories, locations, halal, vegetarian, priceRanges: priceRangeValues(priceBands), userLocation });
  const selected = [...cuisines, ...categories, ...locations, ...priceBands, userLocation ? "Near me" : "", halal ? "Halal" : "", vegetarian ? "Vegetarian" : ""].filter(Boolean);
  const hasDistancePreference = userLocation != null || locations.length > 0;
  const hasRankingPreferences = cuisines.length > 0 || categories.length > 0 || hasDistancePreference;
  const distanceReferences = [...(userLocation ? ["you"] : []), ...locations].join(" or ");
  const locationStatus = geoStatus === "granted"
    ? locations.length ? "Distances use the closest of you or a selected area" : "Distances are measured from you"
    : geoStatus === "denied" ? "Location access denied — pick a named area instead"
    : geoStatus === "unavailable" ? "Couldn't find your location — pick a named area instead"
    : "";

  function openWheel() {
    const visibleVendors = visibleResultsForWheel(recommendations, visibleCount);
    if (visibleVendors.length) setWheelSession(createWheelSession(visibleVendors));
  }

  function removeWheelVendor(vendorId: number) {
    setWheelSession((current) => current
      ? wheelSessionReducer(current, { type: "remove", vendorId })
      : current);
  }

  return (
    <div className="mx-auto w-full max-w-5xl px-5 py-10 sm:px-6 sm:py-14">
      <ol aria-label="Discover steps" className="mb-8 flex items-center justify-center gap-3 text-xs font-semibold sm:text-sm">
        <li aria-current={!showResults ? "step" : undefined} className={!showResults ? "text-primary" : "text-muted-foreground"}>1. Your preferences</li>
        <li aria-hidden="true"><ArrowRight size={15} className="text-muted-foreground" /></li>
        <li aria-current={showResults ? "step" : undefined} className={showResults ? "text-primary" : "text-muted-foreground"}>2. Your food picks</li>
      </ol>

      <header className={`mb-8 ${showResults ? "flex items-center justify-center" : "text-center"}`}>
        {showResults && (
          <button
            type="button"
            onClick={openChat}
            aria-label="Open Foodie chatbot"
            title="Ask Foodie"
            className="group shrink-0 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-primary"
          >
            <img
              src="/ntummy_mascot_yay.png"
              alt=""
              aria-hidden="true"
              className="h-24 w-24 object-contain animate-[mascot-float_2.4s_ease-in-out_infinite] transition-transform group-hover:scale-105 group-active:scale-95"
            />
          </button>
        )}
        <div className="text-center">
          <p className="mb-3 flex items-center justify-center gap-2 text-xs font-bold uppercase tracking-widest text-primary"><Sparkles size={15} aria-hidden="true" /> Find your next favourite</p>
          <h1 ref={headingRef} tabIndex={-1} className="font-display text-3xl font-bold text-foreground outline-none sm:text-4xl">
            {showResults ? "Places that fit your taste" : "What sounds good?"}
          </h1>
          <p className="mx-auto mt-3 max-w-lg text-sm leading-relaxed text-muted-foreground">
            {showResults ? hasRankingPreferences ? "Your preferences come first. More campus food spots stay on the list" : "Explore campus food spots, starting with the best rated" : "Choose what sounds good, or jump straight to your recommendations"}
          </p>
        </div>
      </header>

      {loading && <p role="status" className="rounded-2xl border border-border bg-card p-8 text-center text-sm text-muted-foreground">Finding campus food spots…</p>}
      {!loading && error && (
        <div role="alert" className="rounded-2xl border border-border bg-card p-8 text-center">
          <p className="font-semibold">We couldn't load the food spots</p>
          <p className="mt-2 text-sm text-muted-foreground">{error}</p>
          <button type="button" onClick={() => setAttempt((value) => value + 1)} className="mt-4 cursor-pointer rounded-xl bg-primary px-5 py-3 text-sm font-semibold text-primary-foreground">Try again</button>
        </div>
      )}

      {!loading && !error && !showResults && (
        <form onSubmit={(event) => { event.preventDefault(); setVisibleCount(PAGE_SIZE); setShowResults(true); }} className="mx-auto max-w-2xl rounded-3xl border border-border bg-card p-6 shadow-sm sm:p-8">
          <p className="mb-4 text-sm leading-relaxed text-muted-foreground">Pick as many as you like or leave everything open</p>
          <div className="grid gap-6 sm:grid-cols-2">
            <MultiSelect id="discover-cuisines" label="Cuisine" placeholder="I'm open to anything" icon={<Utensils size={17} className="text-primary" aria-hidden="true" />} options={options.cuisines} selected={cuisines} onChange={setCuisines} />
            <MultiSelect id="discover-categories" label="Category" placeholder="Any type of place" icon={<Store size={17} className="text-primary" aria-hidden="true" />} options={options.categories} selected={categories} onChange={setCategories} />
          </div>

          <div className="mt-6 grid gap-6 sm:grid-cols-2">
            <div className="min-w-0">
              <MultiSelect id="discover-locations" label="Locations" placeholder="Anywhere on campus" icon={<MapPin size={17} className="text-primary" aria-hidden="true" />} options={options.locations} selected={locations} onChange={setLocations} nearMe={{ selected: userLocation != null, busy: geoStatus === "requesting", onToggle: () => { if (userLocation) clearLocation(); else requestLocation(); } }} />
            </div>
            <MultiSelect id="discover-price" label="Price range" placeholder="Any price" icon={<DollarSign size={17} className="text-primary" aria-hidden="true" />} options={PRICE_BAND_OPTIONS} selected={priceBands} onChange={setPriceBands} />
          </div>
          {locationStatus && <p role="status" className="mt-3 text-xs leading-relaxed text-muted-foreground">{locationStatus}</p>}

          <fieldset className="mt-7 border-t border-border pt-6">
            <legend className="float-left mb-3 flex w-full items-center gap-2 text-sm font-semibold"><Leaf size={17} className="text-primary" aria-hidden="true" /> Any dietary preferences?</legend>
            <div className="clear-both flex flex-wrap gap-3">
              {[
                { label: "Halal", checked: halal, onChange: setHalal },
                { label: "Vegetarian", checked: vegetarian, onChange: setVegetarian },
              ].map((choice) => (
                <label key={choice.label} className={`flex cursor-pointer items-center gap-2 rounded-xl border px-4 py-3 text-sm font-semibold ${choice.checked ? "border-primary bg-primary/5 text-primary" : "border-border bg-background text-foreground"}`}>
                  <input type="checkbox" checked={choice.checked} onChange={(event) => choice.onChange(event.target.checked)} className="h-4 w-4 accent-primary" /> {choice.label}
                </label>
              ))}
            </div>
            <p className="mt-3 text-xs leading-relaxed text-muted-foreground">Matches use the dietary information listed by each vendor</p>
          </fieldset>

          <button type="submit" className="mt-8 flex w-full cursor-pointer items-center justify-center gap-2 rounded-xl bg-primary px-5 py-3.5 text-sm font-bold text-primary-foreground transition-opacity hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-primary">
            Show my recommendations <ArrowRight size={17} aria-hidden="true" />
          </button>
          <Link to="/food" className="mt-4 block text-center text-xs font-semibold text-muted-foreground underline-offset-4 hover:underline">Or browse all food spots</Link>
        </form>
      )}

      {!loading && !error && showResults && (
        <section aria-label="Recommended vendors">
          <div className="mb-6 flex flex-col gap-4 rounded-2xl border border-border bg-card p-5 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <div className="flex flex-wrap gap-2">
                {(selected.length ? selected : ["Open to anything"]).map((value) => <span key={value} className="rounded-full bg-primary/5 px-3 py-1 text-xs font-semibold text-primary">{value}</span>)}
              </div>
              <p role="status" className="mt-3 text-xs leading-relaxed text-muted-foreground">{recommendations.length} {recommendations.length === 1 ? "place" : "places"} to explore. {hasRankingPreferences ? "Food preferences and proximity first, with other places included" : "Best rated first"}</p>
              {hasDistancePreference && <p className="mt-2 text-xs leading-relaxed text-muted-foreground">Nearest from {distanceReferences}. Approximate straight-line distances; named areas use their centres.</p>}
            </div>
            <div className="grid shrink-0 grid-cols-2 gap-2">
              <button type="button" onClick={openWheel} disabled={recommendations.length === 0} aria-haspopup="dialog" className="flex cursor-pointer items-center justify-center gap-2 rounded-xl bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50 sm:px-4 sm:py-2.5"><RotateCw size={15} aria-hidden="true" /> Spin the wheel</button>
              <button type="button" onClick={() => setShowResults(false)} className="flex cursor-pointer items-center justify-center gap-2 rounded-xl border border-border px-3 py-1.5 text-xs font-semibold text-foreground hover:bg-muted sm:px-4 sm:py-2.5"><SlidersHorizontal size={15} aria-hidden="true" /> Change preferences</button>
            </div>
          </div>

          {recommendations.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-border bg-card px-6 py-12 text-center">
              <Utensils className="mx-auto mb-4 text-primary" size={28} aria-hidden="true" />
              <h2 className="font-display text-xl font-bold">No places to show this time.</h2>
              <p className="mx-auto mt-3 max-w-md text-sm leading-relaxed text-muted-foreground">{(halal || vegetarian || priceBands.length > 0) ? "No places match all your selected preferences. You can review those choices or try again later." : "There aren't any campus food spots listed yet. Please check back later."}</p>
              <button type="button" onClick={() => setShowResults(false)} className="mt-5 inline-flex cursor-pointer items-center gap-2 rounded-xl bg-primary px-5 py-3 text-sm font-semibold text-primary-foreground"><ArrowLeft size={16} aria-hidden="true" /> Edit preferences</button>
            </div>
          ) : (
            <>
              <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
                {recommendations.slice(0, visibleCount).map((vendor) => {
                  const rating = vendor.average_rating ?? vendor.average_google_rating;
                  return (
                    <Link
                      key={vendor.id}
                      to={`/vendors/${vendor.id}`}
                      className="group min-w-0 rounded-2xl border border-border bg-card overflow-hidden text-foreground no-underline hover:border-primary/25 transition-all duration-300 flex flex-col"
                    >
                      <div className="relative h-44 overflow-hidden bg-muted">
                        {vendor.image_url ? (
                          <img
                            src={apiUrl(vendor.image_url)}
                            alt={`${vendor.name} dish`}
                            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                          />
                        ) : (
                          <div
                            role="img"
                            aria-label={`${vendor.name} has no image`}
                            className="w-full h-full flex items-center justify-center text-sm text-muted-foreground"
                          >
                            No image
                          </div>
                        )}
                        {vendor.cuisine && (
                          <div className="absolute top-3 left-3 flex gap-1.5 flex-wrap">
                            <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-background/75 text-muted-foreground border border-border/60 backdrop-blur-sm">
                              {vendor.cuisine}
                            </span>
                          </div>
                        )}
                        {rating != null && (
                          <div className="absolute top-3 right-3 px-2 py-1 rounded-lg bg-primary text-primary-foreground text-xs font-bold">
                            {rating.toFixed(1)}★
                          </div>
                        )}
                        {(vendor.halal === true || vendor.vegetarian === true) && (
                          <div className="absolute bottom-3 right-3 flex gap-1.5 flex-wrap justify-end">
                            {vendor.halal === true && (
                              <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-background/75 text-foreground border border-border/60 backdrop-blur-sm">
                                Halal
                              </span>
                            )}
                            {vendor.vegetarian === true && (
                              <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-background/75 text-foreground border border-border/60 backdrop-blur-sm">
                                Vegetarian
                              </span>
                            )}
                          </div>
                        )}
                      </div>

                      <div className="p-4 flex flex-col flex-1">
                        {vendor.recommended && (
                          <span className="self-start mb-2 text-xs font-semibold text-primary">
                            Recommended
                          </span>
                        )}

                        <h3 className="font-semibold text-sm leading-snug mb-1">
                          {vendor.name}
                        </h3>

                        <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-3">
                          <MapPin className="w-3 h-3 flex-shrink-0" />
                          {vendor.location || "NTU"}
                        </div>

                        <div className="flex items-center justify-between text-xs text-muted-foreground mb-3">
                          <StarRow rating={rating ?? 0} />
                          <span>{vendor.review_count} reviews</span>
                        </div>

                        <div className="mt-auto border-t border-border pt-3">
                          {hasDistancePreference && (
                            <p className="text-xs font-semibold text-primary mb-3">
                              {vendor.discovery_distance_m != null
                                ? `~${formatDistance(vendor.discovery_distance_m)} from ${vendor.discovery_distance_from}`
                                : vendor.discovery_location_match
                                  ? `In ${vendor.location}`
                                  : "Distance unavailable"}
                            </p>
                          )}
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-bold text-foreground">
                              {vendor.price_range ?? "Price unavailable"}
                            </span>
                            <span className="text-xs text-muted-foreground">
                              {vendor.category}
                            </span>
                          </div>
                        </div>
                      </div>
                    </Link>
                  );
                })}
              </div>
              {visibleCount < recommendations.length && <button type="button" onClick={() => setVisibleCount((value) => value + PAGE_SIZE)} className="mx-auto mt-8 block cursor-pointer rounded-xl border border-border bg-card px-6 py-3 text-sm font-semibold hover:bg-muted">Show more places</button>}
            </>
          )}
        </section>
      )}
      {wheelSession && <VendorWheel context="discover" vendors={wheelSession.vendors} onRemove={removeWheelVendor} onClose={() => setWheelSession(null)} />}
    </div>
  );
}
