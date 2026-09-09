import { useState } from "react";
import { Link } from "react-router-dom";
import { vendorsData } from "../data/vendorsData";

export default function FoodPage() {
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedCanteen, setSelectedCanteen] = useState("All");

  const canteens = ["All", ...new Set(vendorsData.map((vendor) => vendor.canteen))];
  const filteredVendors = vendorsData.filter((vendor) => {
    const normalizedSearch = searchTerm.toLowerCase();
    const matchesSearch =
      vendor.name.toLowerCase().includes(normalizedSearch) ||
      vendor.cuisine.toLowerCase().includes(normalizedSearch);
    const matchesCanteen =
      selectedCanteen === "All" || vendor.canteen === selectedCanteen;
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

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: "24px" }}>
        {filteredVendors.map((vendor) => (
          <div
            key={vendor.id}
            style={{ border: "1px solid var(--border)", borderRadius: "var(--radius-lg)", overflow: "hidden", background: "var(--card)", boxShadow: "var(--shadow)", textAlign: "left" }}
          >
            <img src={vendor.image} alt={vendor.name} style={{ width: "100%", height: "160px", objectFit: "cover" }} />
            <div style={{ padding: "16px", textAlign: "center" }}>
              <span style={{ fontSize: "0.8rem", color: "var(--accent)", background: "var(--accent-bg)", padding: "4px 10px", borderRadius: "999px" }}>
                {vendor.canteen}
              </span>
              <h3 style={{ margin: "10px 0 5px 0", fontFamily: "var(--heading)", color: "var(--text-h)" }}>{vendor.name}</h3>
              <p style={{ margin: "0 0 10px 0", color: "var(--text)", fontSize: "0.9rem" }}>{vendor.cuisine} • ⭐ {vendor.rating}</p>
              <Link
                to={`/food/vendors/${vendor.id}`}
                style={{ display: "inline-block", color: "#fff", background: "var(--accent)", padding: "10px 16px", borderRadius: "var(--radius-lg)", textDecoration: "none", fontSize: "0.9rem", fontWeight: 600 }}
              >
                View Menu & Reviews
              </Link>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
