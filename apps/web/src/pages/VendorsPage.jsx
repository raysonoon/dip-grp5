import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Bot, Send, X } from "lucide-react";

import { DEV_USER_ID } from "../api/client";
import {
  createReview,
  deleteReview,
  fetchVendorReviews,
  reviewImageUrl,
  updateReview,
} from "../api/reviews";
import { fetchVendorById } from "../api/vendors";
import { askChat, chatErrorMessage } from "../api/chat";
import ChatMessageContent from "../components/ChatMessageContent";

const RATING_OPTIONS = [5, 4.5, 4, 3.5, 3, 2.5, 2, 1.5, 1];

function displayError(error) {
  return error instanceof Error ? error.message : "Something went wrong";
}

function displayDate(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
}

export default function VendorsPage() {
  const { vendorId } = useParams();
  const numericVendorId = Number(vendorId);
  const isValidVendorId = Number.isInteger(numericVendorId) && numericVendorId > 0;

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
  const reviewRequestRef = useRef(null);
  const reviewRequestIdRef = useRef(0);

  // Chatbot state
  const [chatMessages, setChatMessages] = useState([
    {
      role: "bot",
      text: "Hey there! I'm Foodie, your NTU campus food guide 🍜 Ask me about canteens, opening hours, or what's good today!",
    },
  ]);
  const [chatInput, setChatInput] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const chatRequestPending = useRef(false);

  async function sendMessage(text) {
    const question = text.trim();
    if (!question || chatRequestPending.current) return;

    chatRequestPending.current = true;
    setChatMessages((prev) => [...prev, { role: "user", text: question }]);
    setChatInput("");
    setIsTyping(true);

    try {
      const response = await askChat(question);
      setChatMessages((prev) => [
        ...prev,
        { role: "bot", text: response.answer, sources: response.sources },
      ]);
    } catch (error) {
      console.error("Chat request failed", error);
      setChatMessages((prev) => [
        ...prev,
        { role: "bot", text: chatErrorMessage(error) },
      ]);
    } finally {
      chatRequestPending.current = false;
      setIsTyping(false);
    }
  }

  const refreshReviews = useCallback(async ({ reset = false } = {}) => {
    if (!isValidVendorId) return;

    const requestId = reviewRequestIdRef.current + 1;
    reviewRequestIdRef.current = requestId;
    reviewRequestRef.current?.abort();
    const controller = new AbortController();
    reviewRequestRef.current = controller;

    setIsLoading(true);
    setLoadError("");
    if (reset) setReviews([]);

    try {
      const page = await fetchVendorReviews(numericVendorId, controller.signal);
      if (requestId === reviewRequestIdRef.current) setReviews(page.items);
    } catch (error) {
      if (requestId === reviewRequestIdRef.current && error.name !== "AbortError") {
        setLoadError(displayError(error));
      }
    } finally {
      if (requestId === reviewRequestIdRef.current) {
        setIsLoading(false);
        if (reviewRequestRef.current === controller) reviewRequestRef.current = null;
      }
    }
  }, [isValidVendorId, numericVendorId]);

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
      reviewRequestIdRef.current += 1;
      reviewRequestRef.current?.abort();
      reviewRequestRef.current = null;
      setReviews([]);
      setIsLoading(false);
      return undefined;
    }

    setActionError("");
    void refreshReviews({ reset: true });

    return () => {
      reviewRequestIdRef.current += 1;
      reviewRequestRef.current?.abort();
      reviewRequestRef.current = null;
    };
  }, [isValidVendorId, loadAttempt, refreshReviews]);

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

  const location = vendor?.location;
  const category = vendor?.category;
  const displayedRating = vendor?.average_rating ?? vendor?.average_google_rating;

  return (
    <>
      {isVendorLoading ? (
        <p style={{ padding: "40px", textAlign: "center" }}>Loading vendor...</p>
      ) : !vendor ? (
        <div style={{ padding: "40px", textAlign: "center", fontFamily: "var(--sans)" }}>
          <h2>Vendor not found</h2>
          {vendorError && <p role="alert">{vendorError}</p>}
          {isValidVendorId && (
            <button type="button" onClick={() => setLoadAttempt((attempt) => attempt + 1)}>
              Try again
            </button>
          )}
          <div style={{ marginTop: "12px" }}>
            <Link to="/food">Back to All Vendors</Link>
          </div>
        </div>
      ) : (
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
            <p style={{ color: "var(--text)" }}>Menu information is not available yet.</p>
          </section>

          <section style={{ marginBottom: "30px" }}>
            <h2 style={{ fontFamily: "var(--heading)", color: "var(--text-h)" }}>Leave a Review</h2>
            <form onSubmit={handleAddReview} style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
              <select value={rating} onChange={(event) => setRating(event.target.value)} style={{ padding: "10px", borderRadius: "6px", border: "1px solid var(--border)" }}>
                {RATING_OPTIONS.map((option) => <option key={option} value={option}>{option} Stars</option>)}
              </select>
              <textarea placeholder="Write an optional review..." value={comment} onChange={(event) => setComment(event.target.value)} rows={3} style={{ padding: "10px", borderRadius: "6px", border: "1px solid var(--border)" }} />
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
              const isOwnReview = DEV_USER_ID !== null && review.user.id === DEV_USER_ID;
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

                  {review.images?.length > 0 && (
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
      )}

      {/* Floating Chatbot Widget */}
      <div className="fixed bottom-6 right-6 z-50 flex flex-col items-end gap-3">
        {chatOpen && (
          <div className="w-[360px] rounded-2xl border border-border bg-card shadow-2xl overflow-hidden">
            <div className="flex items-center justify-between px-5 py-4 border-b border-border bg-card">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-full bg-primary flex items-center justify-center flex-shrink-0">
                  <Bot className="w-4 h-4 text-primary-foreground" />
                </div>
                <div>
                  <div className="text-sm font-semibold text-foreground">Foodie</div>
                  <div className="text-xs text-[#4CAF50] flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-[#4CAF50] inline-block" />
                    Online
                  </div>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setChatOpen(false)}
                className="text-muted-foreground hover:text-foreground transition-colors p-1"
                aria-label="Close chat"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-4 h-72 overflow-y-auto flex flex-col gap-3 bg-background">
              {chatMessages.map((msg, i) => (
                <div
                  key={i}
                  className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                >
                  <div
                    className={`max-w-[82%] px-4 py-2.5 rounded-2xl text-sm leading-relaxed ${
                      msg.role === "user"
                        ? "bg-primary text-primary-foreground rounded-br-sm"
                        : "bg-card border border-border text-foreground rounded-bl-sm"
                    }`}
                  >
                    {msg.role === "bot" ? (
                      <ChatMessageContent answer={msg.text} sources={msg.sources} />
                    ) : (
                      msg.text
                    )}
                  </div>
                </div>
              ))}
              {isTyping && (
                <div className="flex justify-start">
                  <div className="px-4 py-3 rounded-2xl bg-card border border-border rounded-bl-sm">
                    <div className="flex gap-1 items-center">
                      {[0, 1, 2].map((i) => (
                        <div
                          key={i}
                          className="w-1.5 h-1.5 rounded-full bg-muted-foreground animate-bounce"
                          style={{ animationDelay: `${i * 0.15}s` }}
                        />
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </div>

            <div className="px-4 pt-4 pb-4 border-t border-border bg-card">
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && sendMessage(chatInput)}
                  placeholder="Ask anything about campus food..."
                  className="flex-1 bg-background border border-border rounded-xl px-4 py-2.5 text-sm text-foreground placeholder:text-muted-foreground outline-none focus:border-primary/40 transition-colors"
                />
                <button
                  type="button"
                  onClick={() => sendMessage(chatInput)}
                  className="w-10 h-10 rounded-xl bg-primary flex items-center justify-center hover:opacity-90 transition-opacity flex-shrink-0"
                  disabled={isTyping}
                >
                  <Send className="w-4 h-4 text-primary-foreground" />
                </button>
              </div>
            </div>
          </div>
        )}

        <button
          type="button"
          onClick={() => setChatOpen((o) => !o)}
          className="flex items-center gap-2.5 px-5 py-3.5 rounded-full bg-primary text-primary-foreground font-semibold text-sm shadow-lg hover:opacity-90 transition-opacity"
          aria-label="Open Foodie chatbot"
        >
          {chatOpen ? <X className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
          {!chatOpen && "Ask Foodie"}
        </button>
      </div>
    </>
  );
}
