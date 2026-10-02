import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ChevronDown, ChevronLeft, ChevronRight } from "lucide-react";

import { apiUrl } from "../api/client";
import { fetchVendorFilters, fetchVendorPage } from "../api/vendors";

const SEARCH_DEBOUNCE_MS = 300;

function displayError(error) {
  return error instanceof Error ? error.message : "Something went wrong";
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

function FilterSelect({ label, placeholder, value, options, onChange }) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;

    function closeOnOutsideClick(event) {
      if (!containerRef.current?.contains(event.target)) setOpen(false);
    }

    function closeOnEscape(event) {
      if (event.key === "Escape") setOpen(false);
    }

    document.addEventListener("pointerdown", closeOnOutsideClick);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOnOutsideClick);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  return (
    <div ref={containerRef} className="relative w-full sm:w-auto">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={label}
        className="flex w-full sm:w-auto items-center justify-between gap-2 px-3.5 py-2.5 rounded-xl border border-border bg-background text-foreground cursor-pointer"
      >
        <span className={`truncate ${value ? "text-foreground" : "text-muted-foreground"}`}>
          {value || placeholder}
        </span>
        <ChevronDown
          className={`w-4 h-4 flex-shrink-0 text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>
      {open && (
        <ul
          role="listbox"
          className="absolute z-20 mt-1 w-full max-h-60 overflow-auto rounded-xl border border-border bg-background shadow-lg"
        >
          <li
            role="option"
            aria-selected={value === ""}
            onClick={() => {
              onChange("");
              setOpen(false);
            }}
            className={`px-3.5 py-2.5 text-sm cursor-pointer hover:bg-muted ${
              value === "" ? "font-semibold text-foreground" : "text-muted-foreground"
            }`}
          >
            {placeholder}
          </li>
          {options.map((option) => (
            <li
              key={option}
              role="option"
              aria-selected={value === option}
              onClick={() => {
                onChange(option);
                setOpen(false);
              }}
              className={`px-3.5 py-2.5 text-sm cursor-pointer hover:bg-muted ${
                value === option ? "font-semibold text-foreground" : "text-foreground"
              }`}
            >
              {option}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function FoodPage() {
  const PAGE_LIMIT = 12;

  const [searchParams, setSearchParams] = useSearchParams();
  const urlQuery = searchParams.get("q") ?? "";
  const [searchTerm, setSearchTerm] = useState(urlQuery);
  const [debouncedSearchTerm, setDebouncedSearchTerm] = useState(urlQuery.trim());
  const [selectedLocation, setSelectedLocation] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("");

  const [locations, setLocations] = useState([]);
  const [categories, setCategories] = useState([]);

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

  // Load filter dropdown values once
  useEffect(() => {
    const controller = new AbortController();

    fetchVendorFilters(controller.signal)
      .then((filters) => {
        const groupedLocations = [...new Set(filters.locations.map(getLocationGroup))].sort();
        setLocations(groupedLocations);
        setCategories(filters.categories);
      })
      .catch((error) => {
        if (error.name !== "AbortError") {
          console.error("Could not load vendor filters", error);
        }
      });

    return () => controller.abort();
  }, []);

  // Load one filtered/paginated vendor page
  useEffect(() => {
    const controller = new AbortController();

    setIsLoading(true);
    setLoadError("");

    fetchVendorPage({
      q: debouncedSearchTerm,
      location: selectedLocation,
      category: selectedCategory,
      limit: PAGE_LIMIT,
      offset,
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
  }, [debouncedSearchTerm, selectedLocation, selectedCategory, offset, loadAttempt]);

  const hasNextPage = offset + PAGE_LIMIT < total;
  const hasPrevPage = offset > 0;
  const totalPages = Math.ceil(total / PAGE_LIMIT);
  const currentPage = Math.floor(offset / PAGE_LIMIT) + 1;
  const hasActiveFilters = Boolean(searchTerm.trim() || selectedLocation || selectedCategory);

  return (
    <div className="max-w-[1000px] w-full mx-auto px-5 py-10 box-border">
      <header className="mb-8 text-center">
        <h1 className="text-foreground text-3xl font-bold font-display">
          NTU Foodie Hub
        </h1>
        <p className="text-muted-foreground">Explore and review food vendors across NTU canteens</p>
      </header>

      <div className="flex gap-3 mb-6 flex-wrap">
        <input
          type="text"
          placeholder="Search vendor or cuisine..."
          value={searchTerm}
          onChange={(event) => setSearchTerm(event.target.value)}
          className="w-full sm:flex-1 px-3.5 py-2.5 rounded-xl border border-border bg-background text-foreground"
        />
        <FilterSelect
          label="location"
          placeholder="All locations"
          value={selectedLocation}
          options={locations}
          onChange={(value) => {
            setSelectedLocation(value);
            setOffset(0);
          }}
        />
        <FilterSelect
          label="category"
          placeholder="All categories"
          value={selectedCategory}
          options={categories}
          onChange={(value) => {
            setSelectedCategory(value);
            setOffset(0);
          }}
        />
        {hasActiveFilters && (
          <button
            type="button"
            onClick={() => {
              setSearchTerm("");
              setSelectedLocation("");
              setSelectedCategory("");
              setOffset(0);
            }}
            className="w-full sm:w-auto px-3.5 py-2.5 rounded-xl border border-border bg-background text-foreground text-sm font-semibold cursor-pointer hover:bg-muted transition-colors"
          >
            Clear
          </button>
        )}
      </div>

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
              return (
                <div
                  key={vendor.id}
                  className="min-w-0 border border-border rounded-xl overflow-hidden bg-card shadow-sm text-left"
                >
                  {vendor.image_url ? (
                    <img
                      src={apiUrl(vendor.image_url)}
                      alt={vendor.name}
                      className="w-full h-40 object-cover"
                    />
                  ) : (
                    <div
                      role="img"
                      aria-label={`${vendor.name} has no image`}
                      className="w-full h-40 grid place-items-center bg-muted text-muted-foreground"
                    >
                      No image available
                    </div>
                  )}
                  <div className="p-4 text-center">
                    <span className="text-xs text-primary bg-primary/10 px-2.5 py-1 rounded-full">
                      {vendor.location || "NTU"}
                    </span>
                    <h3
                      className="mt-2.5 mb-1 text-foreground font-bold font-display"
                    >
                      {vendor.name}
                    </h3>
                    <p className="mb-2.5 text-muted-foreground text-sm">
                      {vendor.category || "Food"}
                      {rating != null ? ` • ⭐ ${rating}` : ""}
                      {` • ${vendor.review_count} reviews`}
                    </p>
                    <Link
                      to={`/vendors/${vendor.id}`}
                      className="inline-block text-white bg-primary px-4 py-2.5 rounded-xl text-sm font-semibold hover:opacity-90 transition-opacity no-underline"
                    >
                      View Reviews
                    </Link>
                  </div>
                </div>
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