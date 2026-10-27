import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, ArrowRight, Check, Leaf, LocateFixed, MapPin, SlidersHorizontal, Sparkles, Star, Store, Utensils } from "lucide-react";
import { apiUrl } from "../api/client";
import { fetchVendors, type parseVendor } from "../api/vendors";
import { guestDiscoveryOptions, recommendGuestVendors } from "../lib/guestDiscovery.js";
import DiscoverMultiSelect from "../components/DiscoverMultiSelect";
import { formatDistance } from "../lib/vendorRanking.js";

type Vendor = ReturnType<typeof parseVendor>;
type Recommendation = Vendor & {
  discovery_distance_m: number | null;
  discovery_distance_from: string | null;
  discovery_category_match: boolean;
  discovery_location_match: boolean;
};
const PAGE_SIZE = 12;

export default function GuestDiscoverPage() {
  const [vendors, setVendors] = useState<Vendor[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [categories, setCategories] = useState<string[]>([]);
  const [locations, setLocations] = useState<string[]>([]);
  const [userLocation, setUserLocation] = useState<{ lat: number; lng: number } | null>(null);
  const [geoStatus, setGeoStatus] = useState<"idle" | "requesting" | "granted" | "denied" | "unavailable">("idle");
  const [halal, setHalal] = useState(false);
  const [vegetarian, setVegetarian] = useState(false);
  const [showResults, setShowResults] = useState(false);
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
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
    fetchVendors("", controller.signal)
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
  const recommendations: Recommendation[] = recommendGuestVendors(vendors, { categories, locations, halal, vegetarian, userLocation });
  const selected = [...categories, ...locations, userLocation ? "Your current location" : "", halal ? "Halal" : "", vegetarian ? "Vegetarian" : ""].filter(Boolean);
  const hasDistancePreference = userLocation != null || locations.length > 0;
  const hasRankingPreferences = categories.length > 0 || hasDistancePreference;
  const distanceReferences = [...(userLocation ? ["you"] : []), ...locations].join(" or ");
  const locationFallback = locations.length ? `Using ${locations.join(" or ")} instead.` : "Choose a named area above to find nearby places.";
  const locationStatus = geoStatus === "requesting" ? "Finding your current location…"
    : geoStatus === "granted" ? locations.length ? "Your current location is included. Each distance shows its closest starting point: you or a selected area." : "Distances are measured from your current location."
    : geoStatus === "denied" ? `Location access was denied. ${locationFallback}`
    : geoStatus === "unavailable" ? `We couldn't find your current location. ${locationFallback}`
    : "Optional. Include places near you, or choose named areas above.";

  return (
    <div className="mx-auto w-full max-w-5xl px-5 py-10 sm:px-6 sm:py-14">
      <ol aria-label="Discover steps" className="mb-8 flex items-center justify-center gap-3 text-xs font-semibold sm:text-sm">
        <li aria-current={!showResults ? "step" : undefined} className={!showResults ? "text-primary" : "text-muted-foreground"}>1. Your preferences</li>
        <li aria-hidden="true"><ArrowRight size={15} className="text-muted-foreground" /></li>
        <li aria-current={showResults ? "step" : undefined} className={showResults ? "text-primary" : "text-muted-foreground"}>2. Your food picks</li>
      </ol>

      <header className="mb-8 text-center">
        <p className="mb-3 flex items-center justify-center gap-2 text-xs font-bold uppercase tracking-widest text-primary"><Sparkles size={15} aria-hidden="true" /> Find your next favourite</p>
        <h1 ref={headingRef} tabIndex={-1} className="font-display text-3xl font-bold text-foreground outline-none sm:text-4xl">
          {showResults ? "Places that fit your mood." : "What sounds good?"}
        </h1>
        <p className="mx-auto mt-3 max-w-lg text-sm leading-relaxed text-muted-foreground">
          {showResults ? hasRankingPreferences ? "Your preferences come first. More campus food spots stay on the list." : "Explore campus food spots, starting with the best rated." : "Choose what sounds good, or jump straight to your recommendations."}
        </p>
      </header>

      {loading && <p role="status" className="rounded-2xl border border-border bg-card p-8 text-center text-sm text-muted-foreground">Finding campus food spots…</p>}
      {!loading && error && (
        <div role="alert" className="rounded-2xl border border-border bg-card p-8 text-center">
          <p className="font-semibold">We couldn't load the food spots.</p>
          <p className="mt-2 text-sm text-muted-foreground">{error}</p>
          <button type="button" onClick={() => setAttempt((value) => value + 1)} className="mt-4 cursor-pointer rounded-xl bg-primary px-5 py-3 text-sm font-semibold text-primary-foreground">Try again</button>
        </div>
      )}

      {!loading && !error && !showResults && (
        <form onSubmit={(event) => { event.preventDefault(); setVisibleCount(PAGE_SIZE); setShowResults(true); }} className="mx-auto max-w-2xl rounded-3xl border border-border bg-card p-6 shadow-sm sm:p-8">
          <div className="grid gap-6 sm:grid-cols-2">
            <DiscoverMultiSelect id="discover-categories" label="Food types" placeholder="I'm open to anything" icon={<Utensils size={17} className="text-primary" aria-hidden="true" />} options={options.categories} selected={categories} onChange={setCategories} />
            <DiscoverMultiSelect id="discover-locations" label="Locations" placeholder="Anywhere on campus" icon={<MapPin size={17} className="text-primary" aria-hidden="true" />} options={options.locations} selected={locations} onChange={setLocations} />
          </div>
          <p className="mt-3 text-xs leading-relaxed text-muted-foreground">Pick as many as you like, or leave everything open. Your food types and nearby places come first; other spots stay on the list.</p>

          <fieldset className="mt-6 rounded-2xl border border-border p-4">
            <legend className="px-1 text-sm font-semibold">Near you (optional)</legend>
            <div className="flex flex-wrap items-center gap-3">
              <button type="button" disabled={geoStatus === "requesting"} onClick={requestLocation} className="inline-flex cursor-pointer items-center gap-2 rounded-xl border border-border px-4 py-3 text-sm font-semibold hover:bg-muted disabled:cursor-wait disabled:opacity-60"><LocateFixed size={16} className="text-primary" aria-hidden="true" />{geoStatus === "requesting" ? "Finding your location…" : "Use my current location"}</button>
              {(userLocation || geoStatus === "requesting") && <button type="button" onClick={clearLocation} className="cursor-pointer rounded-xl px-3 py-2 text-xs font-semibold text-muted-foreground underline-offset-4 hover:underline">{geoStatus === "requesting" ? "Cancel location request" : "Clear current location"}</button>}
            </div>
            <p role="status" className="mt-3 text-xs leading-relaxed text-muted-foreground">{locationStatus}</p>
          </fieldset>

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
            <p className="mt-3 text-xs leading-relaxed text-muted-foreground">Choose either, both, or leave these open. Matches use the dietary information listed by each vendor.</p>
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
              <p role="status" className="mt-3 text-xs leading-relaxed text-muted-foreground">{recommendations.length} {recommendations.length === 1 ? "place" : "places"} to explore. {hasRankingPreferences ? "Food preferences and proximity first, with other places included." : "Best rated first."}</p>
              {hasDistancePreference && <p className="mt-2 text-xs leading-relaxed text-muted-foreground">Nearest from {distanceReferences}. Approximate straight-line distances; named areas use their centres.</p>}
            </div>
            <button type="button" onClick={() => setShowResults(false)} className="flex shrink-0 cursor-pointer items-center justify-center gap-2 rounded-xl border border-border px-4 py-2.5 text-xs font-semibold text-foreground hover:bg-muted"><SlidersHorizontal size={15} aria-hidden="true" /> Change preferences</button>
          </div>

          {recommendations.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-border bg-card px-6 py-12 text-center">
              <Utensils className="mx-auto mb-4 text-primary" size={28} aria-hidden="true" />
              <h2 className="font-display text-xl font-bold">No places to show this time.</h2>
              <p className="mx-auto mt-3 max-w-md text-sm leading-relaxed text-muted-foreground">{halal || vegetarian ? "We don't have places listed with all your dietary requirements. You can review those choices or try again later." : "There aren't any campus food spots listed yet. Please check back later."}</p>
              <button type="button" onClick={() => setShowResults(false)} className="mt-5 inline-flex cursor-pointer items-center gap-2 rounded-xl bg-primary px-5 py-3 text-sm font-semibold text-primary-foreground"><ArrowLeft size={16} aria-hidden="true" /> Change preferences</button>
            </div>
          ) : (
            <>
              <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
                {recommendations.slice(0, visibleCount).map((vendor) => {
                  const rating = vendor.average_rating ?? vendor.average_google_rating;
                  return (
                    <article key={vendor.id} className="flex min-w-0 flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-sm">
                      {vendor.image_url ? <img src={apiUrl(vendor.image_url)} alt={vendor.name} loading="lazy" className="h-40 w-full object-cover" /> : <div className="grid h-40 place-items-center bg-muted text-muted-foreground"><Store size={36} aria-hidden="true" /></div>}
                      <div className="flex flex-1 flex-col p-5">
                        <p className="flex items-center gap-1.5 text-xs text-muted-foreground"><MapPin size={13} className="shrink-0" aria-hidden="true" /> {vendor.location || "NTU"}</p>
                        <h2 className="mt-2 font-display text-lg font-bold leading-snug">{vendor.name}</h2>
                        <p className="mt-1 text-xs text-muted-foreground">{vendor.category || "Food"}</p>
                        {vendor.discovery_category_match && <p className="mt-3 text-xs font-semibold text-primary">One of your food types</p>}
                        {hasDistancePreference && <p className="mt-2 text-xs text-muted-foreground">{vendor.discovery_distance_m != null ? `~${formatDistance(vendor.discovery_distance_m)} from ${vendor.discovery_distance_from}` : vendor.discovery_location_match ? `In ${vendor.location}` : "Distance unavailable"}</p>}
                        {rating != null && <p className="mt-3 flex items-center gap-1.5 text-xs font-semibold"><Star size={13} className="fill-primary text-primary" aria-hidden="true" /> {rating.toFixed(1)} <span className="font-normal text-muted-foreground">{vendor.average_rating != null ? "Community rating" : "Google rating"}</span></p>}
                        {(halal || vegetarian) && <p className="mt-3 flex items-center gap-1.5 text-xs text-primary"><Check size={13} aria-hidden="true" /> {[halal && "Halal", vegetarian && "Vegetarian"].filter(Boolean).join(" · ")}</p>}
                        <Link to={`/vendors/${vendor.id}`} className="mt-5 flex items-center justify-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground hover:opacity-90">View vendor <ArrowRight size={15} aria-hidden="true" /></Link>
                      </div>
                    </article>
                  );
                })}
              </div>
              {visibleCount < recommendations.length && <button type="button" onClick={() => setVisibleCount((value) => value + PAGE_SIZE)} className="mx-auto mt-8 block cursor-pointer rounded-xl border border-border bg-card px-6 py-3 text-sm font-semibold hover:bg-muted">Show more places</button>}
            </>
          )}
        </section>
      )}
    </div>
  );
}
