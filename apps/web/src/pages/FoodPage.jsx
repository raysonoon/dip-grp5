import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { apiUrl } from "../api/client";
import { fetchVendors } from "../api/vendors";

const DISPLAY_FONT = "'Fraunces', serif";

function displayError(error) {
  return error instanceof Error ? error.message : "Something went wrong";
}

export default function FoodPage() {
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedCanteen, setSelectedCanteen] = useState("All");
  const [vendors, setVendors] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [loadAttempt, setLoadAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setIsLoading(true);
    setLoadError("");

    fetchVendors(controller.signal)
      .then(setVendors)
      .catch((error) => {
        if (error.name !== "AbortError") setLoadError(displayError(error));
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsLoading(false);
      });

    return () => controller.abort();
  }, [loadAttempt]);

  const canteens = [
    "All",
    ...new Set(vendors.map((vendor) => vendor.location).filter(Boolean)),
  ];
  const normalizedSearch = searchTerm.trim().toLowerCase();
  const filteredVendors = vendors.filter((vendor) => {
    const searchableValues = [
      vendor.name,
      vendor.category,
      vendor.location,
      vendor.unit_code,
    ];
    const matchesSearch = searchableValues.some((value) =>
      value?.toLowerCase().includes(normalizedSearch),
    );
    const matchesCanteen =
      selectedCanteen === "All" || vendor.location === selectedCanteen;
    return matchesSearch && matchesCanteen;
  });

  return (
    <div className="max-w-[1000px] w-full mx-auto px-5 py-10 box-border">
      <header className="mb-8 text-center">
        <h1 className="text-foreground text-3xl font-bold" style={{ fontFamily: DISPLAY_FONT }}>
          NTU Foodie Hub
        </h1>
        <p className="text-muted-foreground">Explore and review food vendors across NTU canteens</p>
      </header>

      <div className="flex gap-4 mb-6 flex-wrap">
        <input
          type="text"
          placeholder="Search vendor or cuisine..."
          value={searchTerm}
          onChange={(event) => setSearchTerm(event.target.value)}
          className="flex-1 px-3.5 py-2.5 rounded-xl border border-border bg-background text-foreground"
        />
        <select
          value={selectedCanteen}
          onChange={(event) => setSelectedCanteen(event.target.value)}
          className="px-3.5 py-2.5 rounded-xl border border-border bg-background text-foreground"
        >
          {canteens.map((canteen) => (
            <option key={canteen} value={canteen}>{canteen}</option>
          ))}
        </select>
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
      {!isLoading && !loadError && filteredVendors.length === 0 && (
        <p className="text-center text-muted-foreground">No matching vendors found.</p>
      )}

      {!isLoading && !loadError && (
        <div className="grid gap-6" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))" }}>
          {filteredVendors.map((vendor) => {
            const rating = vendor.average_rating ?? vendor.average_google_rating;
            return (
              <div
                key={vendor.id}
                className="border border-border rounded-xl overflow-hidden bg-card shadow-sm text-left"
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
                    className="mt-2.5 mb-1 text-foreground font-bold"
                    style={{ fontFamily: DISPLAY_FONT }}
                  >
                    {vendor.name}
                  </h3>
                  <p className="mb-2.5 text-muted-foreground text-sm">
                    {vendor.category || "Food"}
                    {rating != null ? ` • ⭐ ${rating}` : ""}
                    {` • ${vendor.review_count} reviews`}
                  </p>
                  <Link
                    to={`/food/vendors/${vendor.id}`}
                    className="inline-block text-white bg-primary px-4 py-2.5 rounded-xl text-sm font-semibold hover:opacity-90 transition-opacity no-underline"
                  >
                    View Reviews
                  </Link>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}