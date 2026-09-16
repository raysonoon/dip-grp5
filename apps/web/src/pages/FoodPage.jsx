import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { apiUrl } from "../api/client";
import { fetchVendors } from "../api/vendors";

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
    <div style={{ maxWidth: "1000px", width: "100%", margin: "0 auto", padding: "40px 20px", fontFamily: "var(--sans)", boxSizing: "border-box" }}>
      <header style={{ marginBottom: "30px", textAlign: "center" }}>
        <h1 style={{ color: "var(--text-h)", fontFamily: "var(--heading)", fontSize: "2.2rem" }}>NTU Foodie Hub</h1>
        <p style={{ color: "var(--text)" }}>Explore and review food vendors across NTU canteens</p>
      </header>

      <div style={{ display: "flex", gap: "15px", marginBottom: "25px", flexWrap: "wrap" }}>
        <input
          type="text"
          placeholder="Search vendor or cuisine..."
          value={searchTerm}
          onChange={(event) => setSearchTerm(event.target.value)}
          style={{ flex: "1", padding: "10px 14px", borderRadius: "var(--radius-lg)", border: "1px solid var(--border)" }}
        />
        <select
          value={selectedCanteen}
          onChange={(event) => setSelectedCanteen(event.target.value)}
          style={{ padding: "10px 14px", borderRadius: "var(--radius-lg)", border: "1px solid var(--border)" }}
        >
          {canteens.map((canteen) => (
            <option key={canteen} value={canteen}>{canteen}</option>
          ))}
        </select>
      </div>

      {isLoading && <p style={{ textAlign: "center", color: "var(--text)" }}>Loading vendors...</p>}
      {!isLoading && loadError && (
        <div role="alert" style={{ textAlign: "center", color: "#b91c1c" }}>
          <p>Could not load vendors: {loadError}</p>
          <button type="button" onClick={() => setLoadAttempt((attempt) => attempt + 1)}>Try again</button>
        </div>
      )}
      {!isLoading && !loadError && filteredVendors.length === 0 && (
        <p style={{ textAlign: "center", color: "var(--text)" }}>No matching vendors found.</p>
      )}

      {!isLoading && !loadError && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: "24px" }}>
          {filteredVendors.map((vendor) => {
            const rating = vendor.average_rating ?? vendor.average_google_rating;
            return (
              <div
                key={vendor.id}
                style={{ border: "1px solid var(--border)", borderRadius: "var(--radius-lg)", overflow: "hidden", background: "var(--card)", boxShadow: "var(--shadow)", textAlign: "left" }}
              >
                {vendor.image_url ? (
                  <img src={apiUrl(vendor.image_url)} alt={vendor.name} style={{ width: "100%", height: "160px", objectFit: "cover" }} />
                ) : (
                  <div role="img" aria-label={`${vendor.name} has no image`} style={{ width: "100%", height: "160px", display: "grid", placeItems: "center", background: "var(--code-bg)", color: "var(--text)" }}>No image available</div>
                )}
                <div style={{ padding: "16px", textAlign: "center" }}>
                  <span style={{ fontSize: "0.8rem", color: "var(--accent)", background: "var(--accent-bg)", padding: "4px 10px", borderRadius: "999px" }}>
                    {vendor.location || "NTU"}
                  </span>
                  <h3 style={{ margin: "10px 0 5px 0", fontFamily: "var(--heading)", color: "var(--text-h)" }}>{vendor.name}</h3>
                  <p style={{ margin: "0 0 10px 0", color: "var(--text)", fontSize: "0.9rem" }}>
                    {vendor.category || "Food"}
                    {rating != null ? ` • ⭐ ${rating}` : ""}
                    {` • ${vendor.review_count} reviews`}
                  </p>
                  <Link
                    to={`/food/vendors/${vendor.id}`}
                    style={{ display: "inline-block", color: "#fff", background: "var(--accent)", padding: "10px 16px", borderRadius: "var(--radius-lg)", textDecoration: "none", fontSize: "0.9rem", fontWeight: 600 }}
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
