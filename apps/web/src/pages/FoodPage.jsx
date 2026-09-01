import React, { useState } from "react";
import { Link } from "react-router-dom";
import { stallsData } from "../data/stallsData";

export default function FoodPage() {
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedCanteen, setSelectedCanteen] = useState("All");

  const canteens = ["All", ...new Set(stallsData.map((stall) => stall.canteen))];

  const filteredStalls = stallsData.filter((stall) => {
    const matchesSearch = stall.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
                          stall.cuisine.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesCanteen = selectedCanteen === "All" || stall.canteen === selectedCanteen;
    return matchesSearch && matchesCanteen;
  });

  return (
    <div style={{ maxWidth: "1000px", margin: "0 auto", padding: "20px", fontFamily: "var(--sans)" }}>
      <header style={{ marginBottom: "30px", textAlign: "center" }}>
        <h1 style={{ color: "var(--text-h)", fontFamily: "var(--heading)", fontSize: "2.2rem" }}>NTU Foodie Hub</h1>
        <p style={{ color: "var(--text)" }}>Explore and review food stalls across NTU canteens</p>
      </header>

      {/* Controls */}
      <div style={{ display: "flex", gap: "15px", marginBottom: "25px", flexWrap: "wrap" }}>
        <input
          type="text"
          placeholder="Search stall or cuisine..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          style={{ flex: "1", padding: "10px 14px", borderRadius: "8px", border: "1px solid var(--border)" }}
        />
        <select
          value={selectedCanteen}
          onChange={(e) => setSelectedCanteen(e.target.value)}
          style={{ padding: "10px 14px", borderRadius: "8px", border: "1px solid var(--border)" }}
        >
          {canteens.map((canteen) => (
            <option key={canteen} value={canteen}>{canteen}</option>
          ))}
        </select>
      </div>

      {/* Stall Grid */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: "20px" }}>
        {filteredStalls.map((stall) => (
          <div key={stall.id} style={{ border: "1px solid var(--border)", borderRadius: "12px", overflow: "hidden", background: "var(--bg)" }}>
            <img src={stall.image} alt={stall.name} style={{ width: "100%", height: "160px", objectFit: "cover" }} />
            <div style={{ padding: "16px" }}>
              <span style={{ fontSize: "0.8rem", color: "var(--accent)", background: "var(--accent-bg)", padding: "4px 8px", borderRadius: "4px" }}>
                {stall.canteen}
              </span>
              <h3 style={{ margin: "10px 0 5px 0", fontFamily: "var(--heading)", color: "var(--text-h)" }}>{stall.name}</h3>
              <p style={{ margin: "0 0 10px 0", color: "var(--text)", fontSize: "0.9rem" }}>{stall.cuisine} • ⭐ {stall.rating}</p>
              <Link to={`/stall/${stall.id}`} style={{ display: "inline-block", color: "#fff", background: "var(--accent)", padding: "8px 12px", borderRadius: "6px", textDecoration: "none", fontSize: "0.9rem" }}>
                View Menu & Reviews
              </Link>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}