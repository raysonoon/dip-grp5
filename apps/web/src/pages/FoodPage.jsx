import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useOutletContext, useSearchParams } from "react-router-dom";
import {
  ArrowUpDown,
  ChevronLeft,
  ChevronRight,
  DollarSign,
  Leaf,
  MapPin,
  SlidersHorizontal,
  Star,
  Tag,
  Utensils,
  X,
} from "lucide-react";
import { apiUrl } from "../api/client";

import { fetchVendorFilters, fetchVendorPage } from "../api/vendors";

import { formatDistance } from "../lib/vendorRanking.js";
import { sortFilterOptions } from "../lib/filterOptions.js";
import { PRICE_BAND_OPTIONS, priceRangeValues } from "../lib/priceRange.js";
import MultiSelect from "../components/MultiSelect";
import SingleSelect from "../components/SingleSelect";
import { useChat } from "../contexts/ChatContext";

const SEARCH_DEBOUNCE_MS = 300;

const SORT_OPTIONS = [
  { value: "recommended", label: "Recommended" },
  { value: "reviews", label: "Most Reviews" },
  { value: "rating", label: "Highest Rating" },
];

function displayError(error) {
  return error instanceof Error ? error.message : "Something went wrong";
}

function normalizeSearchText(value) {
  return value
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

// Return the first dish keyword (from the comma-separated `dishes` field) that
// matches the active search query, so the card can show why it was returned.
function findMatchedDish(dishes, query) {
  if (!dishes || !query) return null;

  const normalizedQuery = normalizeSearchText(query);
  if (!normalizedQuery) return null;

  const tokens = normalizedQuery.split(" ").filter((token) => token.length >= 2);

  for (const rawDish of dishes.split(",")) {
    const dish = rawDish.trim();
    if (!dish) continue;

    const normalizedDish = normalizeSearchText(dish);
    if (
      normalizedDish.includes(normalizedQuery) ||
      tokens.some((token) => normalizedDish.includes(token))
    ) {
      return dish;
    }
  }

  return null;
}

function getLocationGroup(location) {
  const value = location.toLowerCase();

  if (value.includes("north spine")) return "North Spine";
  if (value.includes("south spine")) return "South Spine";
  if (value.includes("north hill")) return "North Hill";
  if (value.includes("tanjong hall")) return "Tanjong Hall";
  if (value.includes("binjai hall")) return "Binjai Hall";
  if (value.includes("the hive")) return "The Hive";
  if (value.includes("the arc")) return "The Arc";
  if (value.includes("nie")) return "NIE";
  if (value.includes("gaia")) return "Gaia";
  if (value.includes("pioneer hall")) return "Pioneer Hall";
  if (value.includes("saraca hall")) return "Saraca Hall";
  if (value.includes("hall 11")) return "Hall 11";
  if (value.includes("hall 13")) return "Hall 13";
  if (value.includes("hall 14")) return "Hall 14";
  if (value.includes("hall 16")) return "Hall 16";
  if (value.includes("hall 1")) return "Hall 1";
  if (value.includes("hall 2")) return "Hall 2";
  if (value.includes("hall 4")) return "Hall 4";
  if (value.includes("hall 9")) return "Hall 9";

  return location;
}

function StarRow({ rating, size = "sm" }) {
  const starClass = size === "sm" ? "w-3.5 h-3.5" : "w-4 h-4";

  return (
    <div className="flex items-center gap-0.5">
      {[1, 2, 3, 4, 5].map((i) => {
        const fill = Math.max(0, Math.min(1, rating - (i - 1)));
        return (
          <span key={i} className="relative inline-block">
            <Star className={`${starClass} fill-transparent text-muted`} />
            <span
              className="absolute inset-0 overflow-hidden"
              style={{ width: `${fill * 100}%` }}
              aria-hidden="true"
            >
              <Star className={`${starClass} fill-primary text-primary`} />
            </span>
          </span>
        );
      })}
    </div>
  );
}

function getPageItems(totalPages, currentPage) {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, i) => i + 1);
  }

  const items = [1];
  const start = Math.max(2, currentPage - 1);
  const end = Math.min(totalPages - 1, currentPage + 1);

  if (start > 2) items.push("start-gap");
  for (let page = start; page <= end; page++) items.push(page);
  if (end < totalPages - 1) items.push("end-gap");
  items.push(totalPages);

  return items;
}

function FilterDialog({ open, onClose, onReset, resultCount, isLoading, children }) {
  useEffect(() => {
    if (!open) return undefined;

    function closeOnEscape(event) {
      if (event.key === "Escape") onClose();
    }

    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[120] flex items-end justify-center sm:items-center">
      <div
        className="absolute inset-0 bg-black/40"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Filter vendors"
        className="relative flex max-h-[85vh] w-full flex-col rounded-t-2xl border border-border bg-background shadow-xl sm:max-w-md sm:rounded-2xl"
      >
        <div className="flex items-center justify-between gap-3 border-b border-border px-5 py-4">
          <h2 className="font-display text-lg font-bold text-foreground">Filters</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close filters"
            className="cursor-pointer rounded-lg p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="flex flex-col gap-5 overflow-y-auto px-5 py-5">
          {children}
        </div>

        <div className="flex items-center justify-between gap-3 border-t border-border px-5 py-4">
          <button
            type="button"
            onClick={onReset}
            className="cursor-pointer text-sm font-semibold text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
          >
            Reset filters
          </button>
          <button
            type="button"
            onClick={onClose}
            className="cursor-pointer rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground hover:opacity-90"
          >
            {isLoading
              ? "Updating…"
              : `Show ${resultCount} ${resultCount === 1 ? "vendor" : "vendors"}`}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function FoodPage() {
  const PAGE_LIMIT = 12;

  const { preferenceStatus, openPreferences } = useOutletContext();
  const { openChat } = useChat();
  const [showPreferencesBanner, setShowPreferencesBanner] = useState(true);
  const [searchParams, setSearchParams] = useSearchParams();

  // Mascot briefly reacts with a happy "yummy" face when clicked.
  const [mascotExpression, setMascotExpression] = useState("satisfied");
  const mascotRevertRef = useRef(null);

  const urlQuery = searchParams.get("q") ?? "";

  const [searchTerm, setSearchTerm] = useState(urlQuery);
  const [debouncedSearchTerm, setDebouncedSearchTerm] = useState(urlQuery.trim());

  const [selectedLocations, setSelectedLocations] = useState([]);
  const [selectedCuisines, setSelectedCuisines] = useState([]);
  const [selectedCategories, setSelectedCategories] = useState([]);
  const [selectedPriceBands, setSelectedPriceBands] = useState([]);
  const [halal, setHalal] = useState(false);
  const [vegetarian, setVegetarian] = useState(false);
  const [isFilterOpen, setIsFilterOpen] = useState(false);

  const [sort, setSort] = useState("recommended");

  // undefined = still detecting, null = unavailable/denied, {lat,lng} = known
  const [userCoords, setUserCoords] = useState(undefined);
  const [geoStatus, setGeoStatus] = useState("idle");
  const [useDistance, setUseDistance] = useState(true);

  const [locations, setLocations] = useState([]);
  const [categories, setCategories] = useState([]);
  const [cuisines, setCuisines] = useState([]);

  const [vendors, setVendors] = useState([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);

  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [loadAttempt, setLoadAttempt] = useState(0);

  // Keep the input and URL query in sync
  useEffect(() => {
    setSearchTerm(urlQuery);
    setDebouncedSearchTerm(urlQuery.trim());
  }, [urlQuery]);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      const query = searchTerm.trim();
      setDebouncedSearchTerm(query);
      setSearchParams(
        (currentParams) => {
          const nextParams = new URLSearchParams(currentParams);
          if (query) nextParams.set("q", query);
          else nextParams.delete("q");
          return nextParams;
        },
        { replace: true }
      );
    }, SEARCH_DEBOUNCE_MS);

    return () => window.clearTimeout(timeoutId);
  }, [searchTerm, setSearchParams]);

  // Ask for the user's location once; the recommended sort uses it to rank
  // nearby vendors. Denied, unsupported or slow -> fall back to A-Z.
  const requestLocation = useCallback(() => {
    if (!("geolocation" in navigator)) {
      setUserCoords(null);
      setGeoStatus("unavailable");
      return;
    }

    setGeoStatus("requesting");

    navigator.geolocation.getCurrentPosition(
      (position) => {
        setUserCoords({
          lat: position.coords.latitude,
          lng: position.coords.longitude,
        });
        setGeoStatus("granted");
      },
      (error) => {
        setUserCoords(null);
        setGeoStatus(error.code === error.PERMISSION_DENIED ? "denied" : "unavailable");
      },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 5 * 60 * 1000 },
    );
  }, []);

  useEffect(() => {
    requestLocation();
  }, [requestLocation]);

  // Load filter dropdown values once
  useEffect(() => {
    const controller = new AbortController();

    fetchVendorFilters(controller.signal)
      .then((filters) => {
        const groupedLocations = sortFilterOptions([...new Set(filters.locations.map(getLocationGroup))]);
        setLocations(groupedLocations);
        setCategories(sortFilterOptions(filters.categories));
        setCuisines(sortFilterOptions(filters.cuisines));
      })
      .catch((error) => {
        if (error.name !== "AbortError") {
          console.error("Could not load vendor filters", error);
        }
      });

    return () => controller.abort();
  }, []);

  // Distance ordering only applies while the "Near me" toggle is on.
  const coords = useDistance ? userCoords : null;
  const isNearby = useDistance && userCoords != null;

  // Load one filtered/paginated vendor page
  useEffect(() => {
    const controller = new AbortController();

    // Wait for the location answer before the first recommended fetch,
    // so the list loads once in the right order instead of twice.
    if (sort === "recommended" && userCoords === undefined) {
      return () => controller.abort();
    }

    setIsLoading(true);
    setLoadError("");

    fetchVendorPage({
      q: debouncedSearchTerm,
      locations: selectedLocations,
      cuisines: selectedCuisines,
      categories: selectedCategories,
      priceRanges: priceRangeValues(selectedPriceBands),
      halal,
      vegetarian,
      sort,
      limit: PAGE_LIMIT,
      offset,
      lat: coords?.lat ?? null,
      lng: coords?.lng ?? null,
      signal: controller.signal,
    })
      .then((page) => {
        setVendors(page.items);
        setTotal(page.total);
      })
      .catch((error) => {
        if (error.name !== "AbortError") {
          setLoadError(displayError(error));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setIsLoading(false);
        }
      });

    return () => controller.abort();
  }, [
    debouncedSearchTerm,
    selectedLocations,
    selectedCuisines,
    selectedCategories,
    selectedPriceBands,
    halal,
    vegetarian,
    sort,
    offset,
    loadAttempt,
    userCoords,
    useDistance,
  ]);

  const hasNextPage = offset + PAGE_LIMIT < total;
  const hasPrevPage = offset > 0;
  const totalPages = Math.ceil(total / PAGE_LIMIT);
  const currentPage = Math.floor(offset / PAGE_LIMIT) + 1;

  const activeFilterCount =
    selectedLocations.length +
    selectedCuisines.length +
    selectedCategories.length +
    selectedPriceBands.length +
    (halal ? 1 : 0) +
    (vegetarian ? 1 : 0);
  const hasActiveFilters = Boolean(searchTerm.trim() || activeFilterCount);
  const isSearching = Boolean(debouncedSearchTerm);

  const clearAllFilters = () => {
    setSearchTerm("");
    setSelectedLocations([]);
    setSelectedCuisines([]);
    setSelectedCategories([]);
    setSelectedPriceBands([]);
    setHalal(false);
    setVegetarian(false);
    setOffset(0);
  };

  const resetDialogFilters = () => {
    setSelectedLocations([]);
    setSelectedCuisines([]);
    setSelectedCategories([]);
    setSelectedPriceBands([]);
    setHalal(false);
    setVegetarian(false);
    setOffset(0);
  };

  const requestNearbyCoords = () => {
    setOffset(0);

    if (isNearby) {
      setUseDistance(false);
      return;
    }

    setUseDistance(true);
    if (userCoords == null) requestLocation();
  };

  useEffect(() => {
    return () => {
      if (mascotRevertRef.current) window.clearTimeout(mascotRevertRef.current);
    };
  }, []);

  const handleMascotClick = () => {
    openChat();
    setMascotExpression("yummy");

    if (mascotRevertRef.current) window.clearTimeout(mascotRevertRef.current);
    mascotRevertRef.current = window.setTimeout(() => {
      setMascotExpression("satisfied");
      mascotRevertRef.current = null;
    }, 2500);
  };

  return (
    <div className="max-w-[1000px] w-full mx-auto px-5 py-10 box-border">
      <header className="mb-8">
        <div className="flex items-center justify-center gap-3">
          <button
            type="button"
            onClick={handleMascotClick}
            aria-label="Open Foodie chatbot"
            title="Ask Foodie"
            className="group shrink-0 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-primary"
          >
            <img
              src={`/ntummy_mascot_${mascotExpression}.png`}
              alt=""
              aria-hidden="true"
              className="h-24 w-24 object-contain animate-[mascot-float_2.4s_ease-in-out_infinite] transition-transform group-hover:scale-105 group-active:scale-95"
            />
          </button>
          <div className="text-center">
            <h1 className="text-foreground text-3xl font-bold font-display">
              NTUmmy Food Hub
            </h1>
            <p className="text-muted-foreground">Discover hidden food gems and find your next meal in NTU</p>
          </div>
        </div>
      </header>

      {preferenceStatus === "skipped" && showPreferencesBanner && (
        <div className="mb-6 flex items-center justify-between gap-4 rounded-xl border border-primary/20 bg-primary/5 px-4 py-3">
          <div>
            <p className="text-sm font-semibold text-foreground">
              Get more personalised food recommendations
            </p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Tell us your food preferences so Foodie can recommend places that suit you.
            </p>
          </div>

          <div className="flex flex-shrink-0 items-center gap-2">
            <button
              type="button"
              onClick={openPreferences}
              className="rounded-lg bg-primary px-3 py-2 text-xs font-semibold text-primary-foreground hover:opacity-90"
            >
              Set preferences
            </button>

            <button
              type="button"
              onClick={() => setShowPreferencesBanner(false)}
              aria-label="Dismiss preferences reminder"
              className="p-1 text-muted-foreground hover:text-foreground"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}

      <div className="flex gap-3 mb-6 flex-wrap">
        <input
          type="text"
          placeholder="Search vendor or cuisine..."
          value={searchTerm}
          onChange={(event) => setSearchTerm(event.target.value)}
          className="w-full sm:flex-1 px-3.5 py-2.5 rounded-xl border border-border bg-background text-foreground"
        />

        <button
          type="button"
          onClick={() => setIsFilterOpen(true)}
          aria-haspopup="dialog"
          aria-expanded={isFilterOpen}
          className={`flex w-full sm:w-auto items-center justify-center gap-2 px-3.5 py-2.5 rounded-xl border text-sm font-semibold cursor-pointer transition-colors ${
            activeFilterCount > 0
              ? "border-primary bg-primary/10 text-primary"
              : "border-border bg-background text-foreground hover:bg-muted"
          }`}
        >
          <SlidersHorizontal className="h-4 w-4" aria-hidden="true" />
          <span>Filters</span>
          {activeFilterCount > 0 && (
            <span className="flex h-5 min-w-5 items-center justify-center rounded-full bg-primary px-1.5 text-xs font-bold text-primary-foreground">
              {activeFilterCount}
            </span>
          )}
        </button>

        <SingleSelect
          id="food-sort"
          label="Sort vendors"
          options={SORT_OPTIONS}
          value={sort}
          onChange={(value) => {
            setSort(value);
            setOffset(0);
          }}
        />

        <button
          type="button"
          onClick={requestNearbyCoords}
          disabled={geoStatus === "requesting"}
          aria-pressed={isNearby}
          title={isNearby ? "Stop sorting by distance" : "Sort vendors by distance from you"}
          className={`w-full sm:w-auto px-3.5 py-2.5 rounded-xl border text-sm font-semibold transition-colors ${
            isNearby
              ? "border-primary bg-primary/10 text-primary cursor-pointer"
              : "border-border bg-background text-foreground cursor-pointer hover:bg-muted"
          } ${geoStatus === "requesting" ? "cursor-wait opacity-70" : ""}`}
        >
          {geoStatus === "requesting" ? "Locating..." : isNearby ? "Nearby ✓" : "Near me"}
        </button>

        {hasActiveFilters && (
          <button
            type="button"
            onClick={clearAllFilters}
            className="w-full sm:w-auto px-3.5 py-2.5 rounded-xl border border-border bg-background text-foreground text-sm font-semibold cursor-pointer hover:bg-muted transition-colors"
          >
            Clear
          </button>
        )}
      </div>

      <FilterDialog
        open={isFilterOpen}
        onClose={() => setIsFilterOpen(false)}
        onReset={resetDialogFilters}
        resultCount={total}
        isLoading={isLoading}
      >
        <MultiSelect
          id="food-filter-locations"
          label="Location"
          placeholder="All locations"
          icon={<MapPin size={17} className="text-primary" aria-hidden="true" />}
          options={locations}
          selected={selectedLocations}
          onChange={(values) => {
            setSelectedLocations(values);
            setOffset(0);
          }}
        />

        <MultiSelect
          id="food-filter-cuisines"
          label="Cuisine"
          placeholder="All cuisines"
          icon={<Utensils size={17} className="text-primary" aria-hidden="true" />}
          options={cuisines}
          selected={selectedCuisines}
          onChange={(values) => {
            setSelectedCuisines(values);
            setOffset(0);
          }}
        />

        <MultiSelect
          id="food-filter-categories"
          label="Category"
          placeholder="All categories"
          icon={<Tag size={17} className="text-primary" aria-hidden="true" />}
          options={categories}
          selected={selectedCategories}
          onChange={(values) => {
            setSelectedCategories(values);
            setOffset(0);
          }}
        />

        <MultiSelect
          id="food-filter-price"
          label="Price range"
          placeholder="Any price"
          icon={<DollarSign size={17} className="text-primary" aria-hidden="true" />}
          options={PRICE_BAND_OPTIONS}
          selected={selectedPriceBands}
          onChange={(values) => {
            setSelectedPriceBands(values);
            setOffset(0);
          }}
        />

        <fieldset>
          <legend className="mb-2 flex items-center gap-2 text-sm font-semibold">
            <Leaf size={17} className="text-primary" aria-hidden="true" />
            Dietary preferences
          </legend>
          <div className="flex flex-wrap gap-2">
            <label
              className={`flex cursor-pointer items-center gap-2 rounded-xl border px-4 py-2.5 text-sm font-semibold ${
                halal
                  ? "border-primary bg-primary/5 text-primary"
                  : "border-border bg-background text-foreground"
              }`}
            >
              <input
                type="checkbox"
                checked={halal}
                onChange={(event) => {
                  setHalal(event.target.checked);
                  setOffset(0);
                }}
                className="h-4 w-4 accent-primary"
              />
              Halal
            </label>

            <label
              className={`flex cursor-pointer items-center gap-2 rounded-xl border px-4 py-2.5 text-sm font-semibold ${
                vegetarian
                  ? "border-primary bg-primary/5 text-primary"
                  : "border-border bg-background text-foreground"
              }`}
            >
              <input
                type="checkbox"
                checked={vegetarian}
                onChange={(event) => {
                  setVegetarian(event.target.checked);
                  setOffset(0);
                }}
                className="h-4 w-4 accent-primary"
              />
              Vegetarian
            </label>
          </div>
        </fieldset>
      </FilterDialog>

      {!isNearby && geoStatus === "denied" && (
        <p className="mb-4 text-center text-sm text-muted-foreground">
          Location access was denied — vendors are shown alphabetically. Allow location in your browser to sort by distance.
        </p>
      )}
      {!isNearby && geoStatus === "unavailable" && (
        <p className="mb-4 text-center text-sm text-muted-foreground">
          We couldn't determine your location — vendors are shown alphabetically.
        </p>
      )}

      {isLoading && <p className="text-center text-muted-foreground">Loading vendors...</p>}

      {!isLoading && loadError && (
        <div role="alert" className="text-center text-destructive">
          <p>Could not load vendors: {loadError}</p>
          <button
            type="button"
            className="cursor-pointer mt-2 underline text-sm font-semibold"
            onClick={() => setLoadAttempt((attempt) => attempt + 1)}
          >
            Try again
          </button>
        </div>
      )}

      {!isLoading && !loadError && vendors.length === 0 && (
        <p className="text-center text-muted-foreground">No matching vendors found.</p>
      )}

      {!isLoading && !loadError && vendors.length > 0 && (
        <>
          <div className="grid gap-6 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3">
            {vendors.map((vendor) => {
              const rating = vendor.average_rating ?? vendor.average_google_rating;
              const matchedDish = isSearching
                ? findMatchedDish(vendor.dishes, debouncedSearchTerm)
                : null;
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

                    {matchedDish && (
                      <p className="mb-3 flex items-center gap-1.5 text-xs text-muted-foreground">
                        <Utensils className="w-3 h-3 flex-shrink-0" aria-hidden="true" />
                        Matched dish: {matchedDish}
                      </p>
                    )}

                    <div className="flex items-center justify-between text-xs text-muted-foreground mb-3">
                      <StarRow rating={rating ?? 0} />
                      <span>{vendor.review_count} reviews</span>
                    </div>

                    <div className="mt-auto border-t border-border pt-3">
                      {vendor.distance_m != null && (
                        <p className="text-xs font-semibold text-primary mb-3">
                          {formatDistance(vendor.distance_m)} from you
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

          {(hasPrevPage || hasNextPage) && (
            <div className="mt-8 overflow-x-auto">
              <div className="flex items-center gap-2 w-max mx-auto">
                <button
                  type="button"
                  disabled={!hasPrevPage}
                  onClick={() => setOffset((prev) => Math.max(0, prev - PAGE_LIMIT))}
                  className={`flex items-center gap-1 px-2 sm:px-4 py-2 text-sm font-semibold ${
                    hasPrevPage ? "cursor-pointer" : "cursor-default opacity-40"
                  }`}
                >
                  <ChevronLeft className="w-4 h-4" />
                  <span className="hidden sm:inline">Previous</span>
                </button>
                {getPageItems(totalPages, currentPage).map((item, index) =>
                  item === "start-gap" || item === "end-gap" ? (
                    <span
                      key={`${item}-${index}`}
                      className="min-w-9 px-1 py-2 text-center text-sm text-muted-foreground"
                    >
                      …
                    </span>
                  ) : (
                    <button
                      key={item}
                      type="button"
                      onClick={() => setOffset((item - 1) * PAGE_LIMIT)}
                      aria-current={currentPage === item ? "page" : undefined}
                      className={`min-w-9 px-2 py-2 rounded-lg border text-sm font-semibold ${
                        currentPage === item
                          ? "bg-primary text-primary-foreground border-primary cursor-default"
                          : "border-border text-foreground cursor-pointer hover:bg-muted"
                      }`}
                    >
                      {item}
                    </button>
                  )
                )}
                <button
                  type="button"
                  disabled={!hasNextPage}
                  onClick={() => setOffset((prev) => prev + PAGE_LIMIT)}
                  className={`flex items-center gap-1 px-2 sm:px-4 py-2 text-sm font-semibold ${
                    hasNextPage ? "cursor-pointer" : "cursor-default opacity-40"
                  }`}
                >
                  <span className="hidden sm:inline">Next</span>
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
