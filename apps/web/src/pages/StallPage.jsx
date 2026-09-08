import React, { useState } from "react";
import { useParams, Link } from "react-router-dom";
import { stallsData } from "../data/stallsData";

export default function StallPage() {
  const { id } = useParams();
  const stall = stallsData.find((s) => s.id === id);

  const [reviews, setReviews] = useState(stall ? stall.reviews : []);
  const [userName, setUserName] = useState("");
  const [rating, setRating] = useState(5);
  const [comment, setComment] = useState("");

  if (!stall) {
    return (
      <div style={{ padding: "40px", textAlign: "center", fontFamily: "var(--sans)" }}>
        <h2>Stall not found</h2>
        <Link to="/">Back to Home</Link>
      </div>
    );
  }

  const handleAddReview = (e) => {
    e.preventDefault();
    if (!userName || !comment) return;
    const newReview = { user: userName, rating: Number(rating), comment };
    setReviews([newReview, ...reviews]);
    setUserName("");
    setComment("");
  };

  return (
    <div style={{ maxWidth: "800px", margin: "0 auto", padding: "20px", fontFamily: "var(--sans)" }}>
      <Link to="/" style={{ textDecoration: "none", color: "var(--accent)" }}>← Back to All Stalls</Link>
      
      <div style={{ marginTop: "15px", marginBottom: "25px" }}>
        <h1 style={{ margin: "0 0 5px 0", fontFamily: "var(--heading)", color: "var(--text-h)" }}>{stall.name}</h1>
        <p style={{ color: "var(--text)", margin: 0 }}>{stall.canteen} | {stall.cuisine} | ⭐ {stall.rating}</p>
      </div>

      {/* Menu Section */}
      <section style={{ marginBottom: "30px", background: "var(--code-bg)", padding: "20px", borderRadius: "10px" }}>
        <h2 style={{ marginTop: 0, fontFamily: "var(--heading)", color: "var(--text-h)" }}>Menu</h2>
        <ul style={{ listStyle: "none", padding: 0 }}>
          {stall.menu.map((item, idx) => (
            <li key={idx} style={{ display: "flex", justifyContent: "space-between", padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
              <span>{item.name}</span>
              <strong>{item.price}</strong>
            </li>
          ))}
        </ul>
      </section>

      {/* Review Form */}
      <section style={{ marginBottom: "30px" }}>
        <h2 style={{ fontFamily: "var(--heading)", color: "var(--text-h)" }}>Leave a Review</h2>
        <form onSubmit={handleAddReview} style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
          <input
            type="text"
            placeholder="Your Name"
            value={userName}
            onChange={(e) => setUserName(e.target.value)}
            style={{ padding: "10px", borderRadius: "6px", border: "1px solid var(--border)" }}
            required
          />
          <select
            value={rating}
            onChange={(e) => setRating(e.target.value)}
            style={{ padding: "10px", borderRadius: "6px", border: "1px solid var(--border)" }}
          >
            <option value={5}>5 Stars - Outstanding</option>
            <option value={4}>4 Stars - Good</option>
            <option value={3}>3 Stars - Average</option>
            <option value={2}>2 Stars - Below Average</option>
            <option value={1}>1 Star - Poor</option>
          </select>
          <textarea
            placeholder="Write your review here..."
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            rows={3}
            style={{ padding: "10px", borderRadius: "6px", border: "1px solid var(--border)" }}
            required
          />
          <button type="submit" style={{ background: "var(--accent)", color: "#fff", padding: "10px", borderRadius: "6px", border: "none", cursor: "pointer", fontFamily: "var(--sans)" }}>
            Submit Review
          </button>
        </form>
      </section>

      {/* Existing Reviews */}
      <section>
        <h2 style={{ fontFamily: "var(--heading)", color: "var(--text-h)" }}>Student Reviews</h2>
        {reviews.map((rev, idx) => (
          <div key={idx} style={{ borderBottom: "1px solid var(--border)", padding: "12px 0" }}>
            <strong>{rev.user}</strong> <span style={{ color: "#eab308" }}>{"★".repeat(rev.rating)}</span>
            <p style={{ margin: "5px 0 0 0", color: "var(--text)" }}>{rev.comment}</p>
          </div>
        ))}
      </section>
    </div>
  );
}