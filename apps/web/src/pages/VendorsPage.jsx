import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { TEST_USER_ID } from "../api/client";
import {
  createReview,
  deleteReview,
  fetchVendorReviews,
  reviewImageUrl,
  updateReview,
} from "../api/reviews";
import { fetchVendorById } from "../api/vendors";
import { vendorsData } from "../data/vendorsData";

const RATING_OPTIONS = [5, 4.5, 4, 3.5, 3, 2.5, 2, 1.5, 1];

function displayError(error) {
  return error instanceof Error ? error.message : "Something went wrong";
}

function displayDate(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export default function VendorsPage() {
  const { vendorId } = useParams();
  const numericVendorId = Number(vendorId);
  const isValidVendorId = Number.isInteger(numericVendorId) && numericVendorId > 0;
  const localVendor = vendorsData.find((item) => item.id === numericVendorId);
  const [vendor, setVendor] = useState(null);
  const [vendorError, setVendorError] = useState("");
  const [isVendorLoading, setIsVendorLoading] = useState(isValidVendorId);
  const [reviews, setReviews] = useState([]);
  const [isLoading, setIsLoading] = useState(isValidVendorId);
  const [loadError, setLoadError] = useState("");
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [actionError, setActionError] = useState("");
  const [isCreating, setIsCreating] = useState(false);
  const [busyReviewId, setBusyReviewId] = useState(null);
  const [editingReviewId, setEditingReviewId] = useState(null);
  const [editRating, setEditRating] = useState(5);
  const [editComment, setEditComment] = useState("");
  const [rating, setRating] = useState(5);
  const [comment, setComment] = useState("");

  const refreshReviews = async () => {
    const page = await fetchVendorReviews(numericVendorId);
    setReviews(page.items);
  };

  useEffect(() => {
    if (!isValidVendorId) {
      setVendor(null);
      setVendorError("Vendor not found");
      setIsVendorLoading(false);
      return undefined;
    }

    const controller = new AbortController();
    setIsVendorLoading(true);
    setVendorError("");
    setVendor(null);
    fetchVendorById(numericVendorId, controller.signal)
      .then(setVendor)
      .catch((error) => {
        if (error.name !== "AbortError") setVendorError(displayError(error));
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsVendorLoading(false);
      });

    return () => controller.abort();
  }, [isValidVendorId, numericVendorId, loadAttempt]);

  useEffect(() => {
    if (!isValidVendorId) {
      setReviews([]);
      setIsLoading(false);
      return undefined;
    }

    const controller = new AbortController();
    setIsLoading(true);
    setLoadError("");
    setActionError("");
    setReviews([]);
    fetchVendorReviews(numericVendorId, controller.signal)
      .then((page) => setReviews(page.items))
      .catch((error) => {
        if (error.name !== "AbortError") setLoadError(displayError(error));
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsLoading(false);
      });

    return () => controller.abort();
  }, [isValidVendorId, numericVendorId, loadAttempt]);

  const handleAddReview = async (event) => {
    event.preventDefault();
    setIsCreating(true);
    setActionError("");
    try {
      await createReview({ vendor_id: numericVendorId, rating: Number(rating), comment: comment.trim() || null });
      setComment("");
      setRating(5);
      await refreshReviews();
    } catch (error) {
      setActionError(displayError(error));
    } finally {
      setIsCreating(false);
    }
  };

  const beginEditing = (review) => {
    setEditingReviewId(review.id);
    setEditRating(review.rating);
    setEditComment(review.comment ?? "");
    setActionError("");
  };

  const handleUpdateReview = async (event, reviewId) => {
    event.preventDefault();
    setBusyReviewId(reviewId);
    setActionError("");
    try {
      await updateReview(reviewId, { rating: Number(editRating), comment: editComment.trim() || null });
      setEditingReviewId(null);
      await refreshReviews();
    } catch (error) {
      setActionError(displayError(error));
    } finally {
      setBusyReviewId(null);
    }
  };

  const handleDeleteReview = async (reviewId) => {
    setBusyReviewId(reviewId);
    setActionError("");
    try {
      await deleteReview(reviewId);
      if (editingReviewId === reviewId) setEditingReviewId(null);
      await refreshReviews();
    } catch (error) {
      setActionError(displayError(error));
    } finally {
      setBusyReviewId(null);
    }
  };

  if (isVendorLoading) {
    return <p style={{ padding: "40px", textAlign: "center" }}>Loading vendor...</p>;
  }

  if (!vendor) {
    return (
      <div style={{ padding: "40px", textAlign: "center", fontFamily: "var(--sans)" }}>
        <h2>Vendor not found</h2>
        {vendorError && <p role="alert">{vendorError}</p>}
        {isValidVendorId && <button type="button" onClick={() => setLoadAttempt((attempt) => attempt + 1)}>Try again</button>}
        <div style={{ marginTop: "12px" }}><Link to="/food">Back to All Vendors</Link></div>
      </div>
    );
  }

  const location = vendor.location || localVendor?.canteen;
  const category = vendor.category || localVendor?.cuisine;
  const displayedRating = vendor.average_rating ?? vendor.average_google_rating ?? localVendor?.rating;

  return (
    <div style={{ maxWidth: "800px", margin: "0 auto", padding: "20px", fontFamily: "var(--sans)" }}>
      <Link to="/food" style={{ textDecoration: "none", color: "var(--accent)" }}>← Back to All Vendors</Link>

      <div style={{ marginTop: "15px", marginBottom: "25px" }}>
        <h1 style={{ margin: "0 0 5px 0", fontFamily: "var(--heading)", color: "var(--text-h)" }}>{vendor.name}</h1>
        <p style={{ color: "var(--text)", margin: 0 }}>
          {[location, category].filter(Boolean).join(" | ")}
          {displayedRating != null ? ` | ⭐ ${displayedRating}` : ""}
        </p>
      </div>

      <section style={{ marginBottom: "30px", background: "var(--code-bg)", padding: "20px", borderRadius: "10px" }}>
        <h2 style={{ marginTop: 0, fontFamily: "var(--heading)", color: "var(--text-h)" }}>Menu</h2>
        {localVendor?.menu?.length ? (
          <ul style={{ listStyle: "none", padding: 0 }}>
            {localVendor.menu.map((item) => (
              <li key={item.name} style={{ display: "flex", justifyContent: "space-between", padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
                <span>{item.name}</span>
                <strong>{item.price}</strong>
              </li>
            ))}
          </ul>
        ) : <p style={{ color: "var(--text)" }}>Menu information is not available yet.</p>}
      </section>

      <section style={{ marginBottom: "30px" }}>
        <h2 style={{ fontFamily: "var(--heading)", color: "var(--text-h)" }}>Leave a Review</h2>
        <form onSubmit={handleAddReview} style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
          <select value={rating} onChange={(event) => setRating(event.target.value)} style={{ padding: "10px", borderRadius: "6px", border: "1px solid var(--border)" }}>
            {RATING_OPTIONS.map((option) => <option key={option} value={option}>{option} Stars</option>)}
          </select>
          <textarea placeholder="Write your review here..." value={comment} onChange={(event) => setComment(event.target.value)} rows={3} style={{ padding: "10px", borderRadius: "6px", border: "1px solid var(--border)" }} required />
          <button type="submit" disabled={isCreating} style={{ background: "var(--accent)", color: "#fff", padding: "10px", borderRadius: "6px", border: "none", cursor: isCreating ? "wait" : "pointer", fontFamily: "var(--sans)", opacity: isCreating ? 0.7 : 1 }}>
            {isCreating ? "Submitting..." : "Submit Review"}
          </button>
        </form>
        {actionError && <p role="alert" style={{ color: "#b91c1c", marginTop: "10px" }}>{actionError}</p>}
      </section>

      <section>
        <h2 style={{ fontFamily: "var(--heading)", color: "var(--text-h)" }}>Student Reviews</h2>
        {isLoading && <p style={{ color: "var(--text)" }}>Loading reviews...</p>}
        {!isLoading && loadError && (
          <div role="alert" style={{ color: "#b91c1c" }}>
            <p>Could not load reviews: {loadError}</p>
            <button type="button" onClick={() => setLoadAttempt((attempt) => attempt + 1)}>Try again</button>
          </div>
        )}
        {!isLoading && !loadError && reviews.length === 0 && <p style={{ color: "var(--text)" }}>No reviews yet. Be the first to leave one.</p>}
        {!isLoading && !loadError && reviews.map((review) => {
          const isOwnReview = review.user.id === TEST_USER_ID;
          const isEditing = editingReviewId === review.id;
          const isBusy = busyReviewId === review.id;
          return (
            <article key={review.id} style={{ borderBottom: "1px solid var(--border)", padding: "16px 0" }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: "12px", flexWrap: "wrap" }}>
                <div>
                  <strong>{review.user.display_name}</strong>
                  {review.user.affiliation && <span style={{ color: "var(--text)", marginLeft: "8px" }}>{review.user.affiliation}</span>}
                  <div style={{ color: "#b7791f", marginTop: "4px" }}>{review.rating} ★</div>
                </div>
                <small style={{ color: "var(--text)" }}>{displayDate(review.created_at)}{review.is_edited ? " (edited)" : ""}</small>
              </div>

              {isEditing ? (
                <form onSubmit={(event) => handleUpdateReview(event, review.id)} style={{ display: "grid", gap: "8px", marginTop: "12px" }}>
                  <select value={editRating} onChange={(event) => setEditRating(event.target.value)}>
                    {RATING_OPTIONS.map((option) => <option key={option} value={option}>{option} Stars</option>)}
                  </select>
                  <textarea value={editComment} onChange={(event) => setEditComment(event.target.value)} rows={3} />
                  <div style={{ display: "flex", gap: "8px" }}>
                    <button type="submit" disabled={isBusy}>{isBusy ? "Saving..." : "Save"}</button>
                    <button type="button" disabled={isBusy} onClick={() => setEditingReviewId(null)}>Cancel</button>
                  </div>
                </form>
              ) : <p style={{ margin: "8px 0 0", color: "var(--text)" }}>{review.comment || "No written comment."}</p>}

              {review.images.length > 0 && (
                <div style={{ display: "flex", gap: "10px", flexWrap: "wrap", marginTop: "12px" }}>
                  {review.images.map((image) => (
                    <img key={image.id} src={reviewImageUrl(review.id, image.id)} alt={`Review by ${review.user.display_name}`} loading="lazy" style={{ width: "120px", height: "90px", objectFit: "cover", borderRadius: "8px" }} />
                  ))}
                </div>
              )}

              {isOwnReview && !isEditing && (
                <div style={{ display: "flex", gap: "8px", marginTop: "12px" }}>
                  <button type="button" disabled={isBusy} onClick={() => beginEditing(review)}>Edit</button>
                  <button type="button" disabled={isBusy} onClick={() => handleDeleteReview(review.id)}>{isBusy ? "Deleting..." : "Delete"}</button>
                </div>
              )}
            </article>
          );
        })}
      </section>
    </div>
  );
}
