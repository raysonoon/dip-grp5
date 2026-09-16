import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { DEV_USER_ID } from "../api/client";
import {
  createReview,
  deleteReview,
  deleteReviewImage,
  fetchVendorReviews,
  reorderReviewImage,
  reviewImageUrl,
  updateReview,
  uploadReviewImage,
} from "../api/reviews";
import { fetchVendorById } from "../api/vendors";

const MAX_IMAGES = 5;
const MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024;
const ALLOWED_MIME_TYPES = ["image/jpeg", "image/png"];

function displayError(error) {
  return error instanceof Error ? error.message : "Something went wrong";
}

function displayDate(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function validateFiles(files, existingCount) {
  if (existingCount + files.length > MAX_IMAGES) {
    return `You can attach at most ${MAX_IMAGES} images per review.`;
  }
  for (const file of files) {
    if (!ALLOWED_MIME_TYPES.includes(file.type)) {
      return "Only JPEG or PNG images are allowed.";
    }
    if (file.size > MAX_FILE_SIZE_BYTES) {
      return `${file.name} is too large. Max file size is 5 MB.`;
    }
  }
  return null;
}

function StarPicker({ value, onChange, disabled }) {
  const [hoverValue, setHoverValue] = useState(null);
  const displayValue = hoverValue ?? value;

  const handlePick = (event, starIndex) => {
    if (disabled) return;
    const { left, width } = event.currentTarget.getBoundingClientRect();
    const isHalf = event.clientX - left < width / 2;
    onChange(isHalf ? starIndex - 0.5 : starIndex);
  };

  const handleHover = (event, starIndex) => {
    if (disabled) return;
    const { left, width } = event.currentTarget.getBoundingClientRect();
    const isHalf = event.clientX - left < width / 2;
    setHoverValue(isHalf ? starIndex - 0.5 : starIndex);
  };

  return (
    <div
      style={{ display: "inline-flex", alignItems: "center", gap: "4px" }}
      onMouseLeave={() => setHoverValue(null)}
      role="radiogroup"
      aria-label="Rating"
    >
      {[1, 2, 3, 4, 5].map((starIndex) => {
        const fillPercent = Math.max(0, Math.min(1, displayValue - (starIndex - 1))) * 100;
        return (
          <div
            key={starIndex}
            style={{ position: "relative", width: "28px", height: "28px", cursor: disabled ? "default" : "pointer" }}
            onMouseMove={(event) => handleHover(event, starIndex)}
            onClick={(event) => handlePick(event, starIndex)}
          >
            <svg viewBox="0 0 24 24" width="28" height="28" style={{ position: "absolute", inset: 0, color: "var(--border)" }} fill="currentColor">
              <path d="M12 2l3.09 6.26L22 9.27l-5 4.87L18.18 21 12 17.27 5.82 21 7 14.14l-5-4.87 6.91-1.01L12 2z" />
            </svg>
            <div style={{ position: "absolute", inset: 0, overflow: "hidden", width: `${fillPercent}%` }}>
              <svg viewBox="0 0 24 24" width="28" height="28" style={{ color: "#b7791f" }} fill="currentColor">
                <path d="M12 2l3.09 6.26L22 9.27l-5 4.87L18.18 21 12 17.27 5.82 21 7 14.14l-5-4.87 6.91-1.01L12 2z" />
              </svg>
            </div>
          </div>
        );
      })}
      {!disabled && (
        <span style={{ marginLeft: "8px", color: "var(--text)", fontSize: "0.9rem" }}>{displayValue.toFixed(1)}</span>
      )}
    </div>
  );
}

// Renders selected-but-not-yet-uploaded files as image previews with a remove (×) button
function FilePreviewGrid({ files, onRemove }) {
  const [previewUrls, setPreviewUrls] = useState([]);

  useEffect(() => {
    const urls = files.map((file) => URL.createObjectURL(file));
    setPreviewUrls(urls);
    return () => {
      urls.forEach((url) => URL.revokeObjectURL(url));
    };
  }, [files]);

  if (files.length === 0) return null;

  return (
    <div style={{ display: "flex", gap: "10px", flexWrap: "wrap", marginTop: "10px" }}>
      {files.map((file, index) => (
        <div key={`${file.name}-${index}`} style={{ position: "relative" }}>
          <img
            src={previewUrls[index]}
            alt={file.name}
            style={{ width: "80px", height: "80px", objectFit: "cover", borderRadius: "8px", border: "1px solid var(--border)" }}
          />
          <button
            type="button"
            onClick={() => onRemove(index)}
            aria-label={`Remove ${file.name}`}
            style={{
              position: "absolute",
              top: "-8px",
              right: "-8px",
              width: "22px",
              height: "22px",
              borderRadius: "50%",
              background: "#b91c1c",
              color: "#fff",
              border: "2px solid var(--bg)",
              cursor: "pointer",
              fontSize: "0.75rem",
              lineHeight: 1,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              padding: 0,
            }}
          >
            ✕
          </button>
        </div>
      ))}
    </div>
  );
}

// A clearer, clickable upload region with drag-and-drop styling
function UploadDropzone({ onFilesSelected, label }) {
  return (
    <label
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: "6px",
        padding: "20px",
        border: "2px dashed var(--border)",
        borderRadius: "8px",
        cursor: "pointer",
        textAlign: "center",
        color: "var(--text)",
        background: "var(--code-bg)",
      }}
    >
      <span style={{ fontSize: "1.4rem" }}>📷</span>
      <span style={{ fontSize: "0.85rem", fontWeight: 600 }}>{label}</span>
      <span style={{ fontSize: "0.75rem", color: "var(--muted-foreground, var(--text))" }}>
        Click to browse — JPEG or PNG, max 5MB each
      </span>
      <input
        type="file"
        accept="image/jpeg,image/png"
        multiple
        onChange={(event) => onFilesSelected(Array.from(event.target.files))}
        style={{ display: "none", cursor: "pointer" }}
      />
    </label>
  );
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
  const [deletingReviewId, setDeletingReviewId] = useState(null);
  const [editingReviewId, setEditingReviewId] = useState(null);
  const [editRating, setEditRating] = useState(5);
  const [editComment, setEditComment] = useState("");
  const [editNewFiles, setEditNewFiles] = useState([]);
  const [rating, setRating] = useState(5);
  const [comment, setComment] = useState("");
  const [newFiles, setNewFiles] = useState([]);
  const [deleteTargetId, setDeleteTargetId] = useState(null);
  const reviewRequestRef = useRef(null);
  const reviewRequestIdRef = useRef(0);

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

  const addNewFiles = (files) => {
    setNewFiles((prev) => [...prev, ...files]);
  };

  const removeNewFile = (index) => {
    setNewFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const addEditFiles = (files) => {
    setEditNewFiles((prev) => [...prev, ...files]);
  };

  const removeEditFile = (index) => {
    setEditNewFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const handleAddReview = async (event) => {
    event.preventDefault();
    setActionError("");

    const validationError = validateFiles(newFiles, 0);
    if (validationError) {
      setActionError(validationError);
      return;
    }

    setIsCreating(true);
    try {
      const created = await createReview({
        vendor_id: numericVendorId,
        rating: Number(rating),
        comment: comment.trim() || null,
      });

      for (const file of newFiles) {
        try {
          await uploadReviewImage(created.id, file);
        } catch (uploadError) {
          setActionError(`Review submitted, but an image failed to upload: ${displayError(uploadError)}`);
        }
      }

      setComment("");
      setRating(5);
      setNewFiles([]);
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
    setEditNewFiles([]);
    setActionError("");
  };

  const handleUpdateReview = async (event, review) => {
    event.preventDefault();
    setActionError("");

    const validationError = validateFiles(editNewFiles, review.images.length);
    if (validationError) {
      setActionError(validationError);
      return;
    }

    setBusyReviewId(review.id);
    try {
      await updateReview(review.id, { rating: Number(editRating), comment: editComment.trim() || null });

      for (const file of editNewFiles) {
        try {
          await uploadReviewImage(review.id, file);
        } catch (uploadError) {
          setActionError(`Saved, but an image failed to upload: ${displayError(uploadError)}`);
        }
      }

      setEditingReviewId(null);
      setEditNewFiles([]);
      await refreshReviews();
    } catch (error) {
      setActionError(displayError(error));
    } finally {
      setBusyReviewId(null);
    }
  };

  const handleDeleteReviewImage = async (reviewId, imageId) => {
    setActionError("");
    try {
      await deleteReviewImage(reviewId, imageId);
      await refreshReviews();
    } catch (error) {
      setActionError(displayError(error));
    }
  };

  const handleReorderReviewImage = async (review, imageId, direction) => {
    setActionError("");
    const sorted = [...review.images].sort((a, b) => a.display_order - b.display_order);
    const index = sorted.findIndex((image) => image.id === imageId);
    const swapIndex = direction === "up" ? index - 1 : index + 1;
    if (swapIndex < 0 || swapIndex >= sorted.length) return;

    const current = sorted[index];
    const swapWith = sorted[swapIndex];

    try {
      await reorderReviewImage(review.id, current.id, 99);
      await reorderReviewImage(review.id, swapWith.id, current.display_order);
      await reorderReviewImage(review.id, current.id, swapWith.display_order);
      await refreshReviews();
    } catch (error) {
      setActionError(displayError(error));
      await refreshReviews();
    }
  };

  const requestDeleteReview = (reviewId) => {
    setDeleteTargetId(reviewId);
  };

  const cancelDeleteReview = () => {
    setDeleteTargetId(null);
  };

  const confirmDeleteReview = async () => {
    if (deleteTargetId === null) return;
    const reviewId = deleteTargetId;
    setDeletingReviewId(reviewId);
    setBusyReviewId(reviewId);
    setActionError("");
    try {
      await deleteReview(reviewId);
      if (editingReviewId === reviewId) setEditingReviewId(null);
      setDeleteTargetId(null);
      await refreshReviews();
    } catch (error) {
      setActionError(displayError(error));
      setDeleteTargetId(null);
    } finally {
      setBusyReviewId(null);
      setDeletingReviewId(null);
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
        {isValidVendorId && (
          <button type="button" style={{ cursor: "pointer" }} onClick={() => setLoadAttempt((attempt) => attempt + 1)}>
            Try again
          </button>
        )}
        <div style={{ marginTop: "12px" }}>
          <Link to="/food">Back to All Vendors</Link>
        </div>
      </div>
    );
  }

  const location = vendor.location;
  const category = vendor.category;
  const displayedRating = vendor.average_rating ?? vendor.average_google_rating;

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
        <p style={{ color: "var(--text)" }}>Menu information is not available yet.</p>
      </section>

      <section style={{ marginBottom: "30px" }}>
        <h2 style={{ fontFamily: "var(--heading)", color: "var(--text-h)" }}>Leave a Review</h2>
        <form onSubmit={handleAddReview} style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
          <div>
            <StarPicker value={rating} onChange={setRating} disabled={isCreating} />
          </div>
          <textarea
            placeholder="Write your review here..."
            value={comment}
            onChange={(event) => setComment(event.target.value)}
            rows={3}
            style={{ padding: "10px", borderRadius: "6px", border: "1px solid var(--border)" }}
            required
          />
          <div>
            <UploadDropzone onFilesSelected={addNewFiles} label="Add photos to your review" />
            <FilePreviewGrid files={newFiles} onRemove={removeNewFile} />
          </div>
          <button
            type="submit"
            disabled={isCreating}
            style={{
              background: "var(--accent)",
              color: "#fff",
              padding: "10px",
              borderRadius: "6px",
              border: "none",
              cursor: isCreating ? "wait" : "pointer",
              fontFamily: "var(--sans)",
              opacity: isCreating ? 0.7 : 1,
            }}
          >
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
            <button type="button" style={{ cursor: "pointer" }} onClick={() => setLoadAttempt((attempt) => attempt + 1)}>
              Try again
            </button>
          </div>
        )}
        {!isLoading && !loadError && reviews.length === 0 && (
          <p style={{ color: "var(--text)" }}>No reviews yet. Be the first to leave one.</p>
        )}
        {!isLoading && !loadError && reviews.map((review) => {
          const isOwnReview = DEV_USER_ID !== null && review.user.id === DEV_USER_ID;
          const isEditing = editingReviewId === review.id;
          const isBusy = busyReviewId === review.id;
          const sortedImages = [...review.images].sort((a, b) => a.display_order - b.display_order);

          return (
            <article key={review.id} style={{ borderBottom: "1px solid var(--border)", padding: "16px 0" }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: "12px", flexWrap: "wrap" }}>
                <div>
                  <strong>{review.user.display_name}</strong>
                  {review.user.affiliation && <span style={{ color: "var(--text)", marginLeft: "8px" }}>{review.user.affiliation}</span>}
                  {/* Read-only stars: only shown when NOT editing, to avoid the duplicate picker */}
                  {!isEditing && (
                    <div style={{ marginTop: "4px" }}>
                      <StarPicker value={review.rating} onChange={() => {}} disabled />
                    </div>
                  )}
                </div>
                <small style={{ color: "var(--text)" }}>
                  {displayDate(review.created_at)}
                  {review.is_edited ? " (edited)" : ""}
                </small>
              </div>

              {isEditing ? (
                <form onSubmit={(event) => handleUpdateReview(event, review)} style={{ display: "grid", gap: "8px", marginTop: "12px" }}>
                  {/* Only ONE star picker here, the editable one */}
                  <StarPicker value={editRating} onChange={setEditRating} disabled={isBusy} />
                  <textarea value={editComment} onChange={(event) => setEditComment(event.target.value)} rows={3} />

                  {sortedImages.length > 0 && (
                    <div>
                      <label style={{ display: "block", marginBottom: "6px", color: "var(--text)", fontSize: "0.9rem" }}>
                        Existing photos
                      </label>
                      <div style={{ display: "flex", gap: "10px", flexWrap: "wrap" }}>
                        {sortedImages.map((image, index) => (
                          <div key={image.id}>
                            <img
                              src={reviewImageUrl(review.id, image.id)}
                              alt={`Review by ${review.user.display_name}`}
                              loading="lazy"
                              style={{ width: "90px", height: "68px", objectFit: "cover", borderRadius: "6px", border: "1px solid var(--border)" }}
                            />
                            <div style={{ display: "flex", justifyContent: "center", gap: "6px", marginTop: "4px" }}>
                              <button
                                type="button"
                                disabled={index === 0 || isBusy}
                                style={{ cursor: index === 0 || isBusy ? "default" : "pointer", fontSize: "0.75rem" }}
                                onClick={() => handleReorderReviewImage(review, image.id, "up")}
                              >
                                ←
                              </button>
                              <button
                                type="button"
                                disabled={isBusy}
                                style={{ cursor: isBusy ? "default" : "pointer", fontSize: "0.75rem", color: "#b91c1c" }}
                                onClick={() => handleDeleteReviewImage(review.id, image.id)}
                              >
                                ✕
                              </button>
                              <button
                                type="button"
                                disabled={index === sortedImages.length - 1 || isBusy}
                                style={{ cursor: index === sortedImages.length - 1 || isBusy ? "default" : "pointer", fontSize: "0.75rem" }}
                                onClick={() => handleReorderReviewImage(review, image.id, "down")}
                              >
                                →
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  <div>
                    <UploadDropzone onFilesSelected={addEditFiles} label="Add more photos" />
                    <FilePreviewGrid files={editNewFiles} onRemove={removeEditFile} />
                  </div>

                  <div style={{ display: "flex", gap: "8px" }}>
                    <button type="submit" disabled={isBusy} style={{ cursor: isBusy ? "wait" : "pointer" }}>
                      {isBusy ? "Saving..." : "Save"}
                    </button>
                    <button
                      type="button"
                      disabled={isBusy}
                      style={{ cursor: isBusy ? "default" : "pointer" }}
                      onClick={() => {
                        setEditingReviewId(null);
                        setEditNewFiles([]);
                      }}
                    >
                      Cancel
                    </button>
                  </div>
                </form>
              ) : (
                <p style={{ margin: "8px 0 0", color: "var(--text)" }}>{review.comment || "No written comment."}</p>
              )}

              {!isEditing && sortedImages.length > 0 && (
                <div style={{ display: "flex", gap: "10px", flexWrap: "wrap", marginTop: "12px" }}>
                  {sortedImages.map((image) => (
                    <img
                      key={image.id}
                      src={reviewImageUrl(review.id, image.id)}
                      alt={`Review by ${review.user.display_name}`}
                      loading="lazy"
                      style={{ width: "120px", height: "90px", objectFit: "cover", borderRadius: "8px" }}
                    />
                  ))}
                </div>
              )}

              {isOwnReview && !isEditing && (
                <div style={{ display: "flex", gap: "8px", marginTop: "12px" }}>
                  <button type="button" disabled={isBusy} style={{ cursor: isBusy ? "default" : "pointer" }} onClick={() => beginEditing(review)}>
                    Edit
                  </button>
                  <button
                    type="button"
                    disabled={deletingReviewId === review.id}
                    style={{ cursor: deletingReviewId === review.id ? "default" : "pointer", opacity: deletingReviewId === review.id ? 0.6 : 1 }}
                    onClick={() => requestDeleteReview(review.id)}
                  >
                    Delete
                  </button>
                </div>
              )}
            </article>
          );
        })}
      </section>

      {deleteTargetId !== null && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 50 }}>
          <div
            style={{
              background: "var(--card, var(--bg))",
              borderRadius: "10px",
              padding: "24px",
              maxWidth: "360px",
              width: "90%",
              border: "1px solid var(--border)",
              boxShadow: "0 10px 40px rgba(0,0,0,0.35)",
            }}
          >
            <h3 style={{ marginTop: 0, fontFamily: "var(--heading)", color: "var(--text-h)" }}>Delete this review?</h3>
            <p style={{ color: "var(--text)", fontSize: "0.9rem" }}>
              This action cannot be undone. The review and its photos will be permanently removed.
            </p>
            <div style={{ display: "flex", gap: "10px", justifyContent: "flex-end", marginTop: "16px" }}>
              <button
                type="button"
                disabled={deletingReviewId !== null}
                style={{ cursor: deletingReviewId !== null ? "default" : "pointer" }}
                onClick={cancelDeleteReview}
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={deletingReviewId !== null}
                style={{
                  cursor: deletingReviewId !== null ? "default" : "pointer",
                  background: "#b91c1c",
                  color: "#fff",
                  border: "none",
                  padding: "8px 14px",
                  borderRadius: "6px",
                  opacity: deletingReviewId !== null ? 0.6 : 1,
                }}
                onClick={confirmDeleteReview}
              >
                {deletingReviewId !== null ? "Deleting..." : "Delete"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}