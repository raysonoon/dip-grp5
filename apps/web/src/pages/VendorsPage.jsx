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
const DISPLAY_FONT = "'Fraunces', serif";

function displayError(error) {
  return error instanceof Error ? error.message : "Something went wrong";
}

function displayDate(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
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
      className="inline-flex items-center gap-1"
      onMouseLeave={() => setHoverValue(null)}
      role="radiogroup"
      aria-label="Rating"
    >
      {[1, 2, 3, 4, 5].map((starIndex) => {
        const fillPercent = Math.max(0, Math.min(1, displayValue - (starIndex - 1))) * 100;
        return (
          <div
            key={starIndex}
            className={`relative w-7 h-7 ${disabled ? "" : "cursor-pointer"}`}
            onMouseMove={(event) => handleHover(event, starIndex)}
            onClick={(event) => handlePick(event, starIndex)}
          >
            <svg viewBox="0 0 24 24" className="w-7 h-7 absolute inset-0 text-border" fill="currentColor">
              <path d="M12 2l3.09 6.26L22 9.27l-5 4.87L18.18 21 12 17.27 5.82 21 7 14.14l-5-4.87 6.91-1.01L12 2z" />
            </svg>
            <div className="absolute inset-0 overflow-hidden" style={{ width: `${fillPercent}%` }}>
              <svg viewBox="0 0 24 24" className="w-7 h-7 text-primary" fill="currentColor">
                <path d="M12 2l3.09 6.26L22 9.27l-5 4.87L18.18 21 12 17.27 5.82 21 7 14.14l-5-4.87 6.91-1.01L12 2z" />
              </svg>
            </div>
          </div>
        );
      })}
      {!disabled && <span className="ml-2 text-sm text-muted-foreground">{displayValue.toFixed(1)}</span>}
    </div>
  );
}

function FilePreviewGrid({ files, onRemove, onReorder }) {
  const [previewUrls, setPreviewUrls] = useState([]);

  useEffect(() => {
    const urls = files.map((file) => URL.createObjectURL(file));
    setPreviewUrls(urls);
    return () => urls.forEach((url) => URL.revokeObjectURL(url));
  }, [files]);

  if (files.length === 0) return null;

  return (
    <div className="flex gap-3 flex-wrap mt-3">
      {files.map((file, index) => (
        <div key={`${file.name}-${index}`}>
          <div className="relative">
            <img
              src={previewUrls[index]}
              alt={file.name}
              className="w-20 h-20 object-cover rounded-lg border border-border"
            />
            <button
              type="button"
              onClick={() => onRemove(index)}
              aria-label={`Remove ${file.name}`}
              className="absolute -top-2 -right-2 w-[22px] h-[22px] rounded-full bg-destructive text-white border-2 border-background cursor-pointer text-xs flex items-center justify-center p-0"
            >
              ✕
            </button>
          </div>
          {onReorder && (
            <div className="flex justify-center gap-1.5 mt-1">
              <button
                type="button"
                disabled={index === 0}
                className={`text-xs ${index === 0 ? "cursor-default opacity-40" : "cursor-pointer"}`}
                onClick={() => onReorder(index, index - 1)}
              >
                ←
              </button>
              <button
                type="button"
                disabled={index === files.length - 1}
                className={`text-xs ${index === files.length - 1 ? "cursor-default opacity-40" : "cursor-pointer"}`}
                onClick={() => onReorder(index, index + 1)}
              >
                →
              </button>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function UploadDropzone({ onFilesSelected, label }) {
  return (
    <label className="flex flex-col items-center justify-center gap-1.5 p-5 rounded-lg border-2 border-dashed border-border cursor-pointer text-center text-muted-foreground bg-muted hover:border-primary/40 transition-colors">
      <span className="text-2xl">📷</span>
      <span className="text-sm font-semibold text-foreground">{label}</span>
      <span className="text-xs text-muted-foreground">Click to browse — JPEG or PNG, max 5MB each</span>
      <input
        type="file"
        accept="image/jpeg,image/png"
        multiple
        onChange={(event) => {
          onFilesSelected(Array.from(event.target.files));
          event.target.value = "";
        }}
        className="hidden"
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
  const [reorderingReviewId, setReorderingReviewId] = useState(null);
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

  const refreshReviews = useCallback(
    async ({ reset = false } = {}) => {
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
    },
    [isValidVendorId, numericVendorId]
  );

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
    setActionError("");
    refreshReviews({ reset: true });
    return () => reviewRequestRef.current?.abort();
  }, [refreshReviews, loadAttempt]);

  const addNewFiles = (files) => setNewFiles((prev) => [...prev, ...files]);
  const removeNewFile = (index) => setNewFiles((prev) => prev.filter((_, i) => i !== index));
  const reorderNewFiles = (fromIndex, toIndex) => {
    setNewFiles((prev) => {
      const updated = [...prev];
      const [moved] = updated.splice(fromIndex, 1);
      updated.splice(toIndex, 0, moved);
      return updated;
    });
  };
  const addEditFiles = (files) => setEditNewFiles((prev) => [...prev, ...files]);
  const removeEditFile = (index) => setEditNewFiles((prev) => prev.filter((_, i) => i !== index));
  const reorderEditFiles = (fromIndex, toIndex) => {
    setEditNewFiles((prev) => {
      const updated = [...prev];
      const [moved] = updated.splice(fromIndex, 1);
      updated.splice(toIndex, 0, moved);
      return updated;
    });
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
      await refreshReviews({ reset: true });
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
      await refreshReviews({ reset: true });
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
      await refreshReviews({ reset: true });
    } catch (error) {
      setActionError(displayError(error));
    }
  };

  const handleReorderReviewImage = async (review, imageId, direction) => {
    if (reorderingReviewId === review.id) return;
    setReorderingReviewId(review.id);
    setActionError("");

    try {
      const sorted = [...review.images].sort((a, b) => a.display_order - b.display_order);
      const index = sorted.findIndex((image) => image.id === imageId);
      const swapIndex = direction === "up" ? index - 1 : index + 1;
      if (swapIndex < 0 || swapIndex >= sorted.length) return;

      const current = sorted[index];
      const swapWith = sorted[swapIndex];

      const usedOrders = new Set(sorted.map((image) => image.display_order));
      const freeOrder = [1, 2, 3, 4, 5].find((order) => !usedOrders.has(order));

      if (freeOrder === undefined) {
        setActionError(
          "Can't reorder — this review has 5 images with no free slot available for reordering."
        );
        return;
      }

      await reorderReviewImage(review.id, current.id, freeOrder);
      await reorderReviewImage(review.id, swapWith.id, current.display_order);
      await reorderReviewImage(review.id, current.id, swapWith.display_order);
      await refreshReviews({ reset: true });
    } catch (error) {
      setActionError(displayError(error));
      await refreshReviews({ reset: true });
    } finally {
      setReorderingReviewId(null);
    }
  };

  const requestDeleteReview = (reviewId) => setDeleteTargetId(reviewId);
  const cancelDeleteReview = () => setDeleteTargetId(null);

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
      await refreshReviews({ reset: true });
    } catch (error) {
      setActionError(displayError(error));
      setDeleteTargetId(null);
    } finally {
      setBusyReviewId(null);
      setDeletingReviewId(null);
    }
  };

  if (isVendorLoading) {
    return <p className="p-10 text-center text-muted-foreground">Loading vendor...</p>;
  }

  if (!vendor) {
    return (
      <div className="p-10 text-center">
        <h2 className="text-xl font-bold text-foreground">Vendor not found</h2>
        {vendorError && <p role="alert" className="text-destructive mt-2">{vendorError}</p>}
        {isValidVendorId && (
          <button
            type="button"
            className="cursor-pointer mt-3 px-4 py-2 rounded-lg border border-border text-sm font-semibold"
            onClick={() => setLoadAttempt((attempt) => attempt + 1)}
          >
            Try again
          </button>
        )}
        <div className="mt-3">
          <Link to="/food" className="text-primary hover:underline">Back to All Vendors</Link>
        </div>
      </div>
    );
  }

  const location = vendor.location;
  const category = vendor.category;
  const displayedRating = vendor.average_rating ?? vendor.average_google_rating;

  return (
    <div className="max-w-3xl mx-auto px-6 py-10">
      <Link to="/food" className="text-primary hover:underline text-sm font-medium">
        ← Back to All Vendors
      </Link>

      <div className="mt-4 mb-6">
        <h1 className="text-2xl font-bold text-foreground" style={{ fontFamily: DISPLAY_FONT }}>
          {vendor.name}
        </h1>
        <p className="text-muted-foreground mt-1">
          {[location, category].filter(Boolean).join(" | ")}
          {displayedRating != null ? ` | ⭐ ${displayedRating}` : ""}
        </p>
      </div>

      <section className="mb-8 bg-card border border-border p-5 rounded-xl">
        <h2 className="text-lg font-bold text-foreground mb-3">Menu</h2>
        <p className="text-muted-foreground">Menu information is not available yet.</p>
      </section>

      <section className="mb-8">
        <h2 className="text-lg font-bold text-foreground mb-3">Leave a Review</h2>
        <form onSubmit={handleAddReview} className="flex flex-col gap-3">
          <StarPicker value={rating} onChange={setRating} disabled={isCreating} />
          <textarea
            placeholder="Write your review here..."
            value={comment}
            onChange={(event) => setComment(event.target.value)}
            rows={3}
            className="p-3 rounded-lg border border-border bg-background text-sm resize-y"
            required
          />
          <div>
            <UploadDropzone onFilesSelected={addNewFiles} label="Add photos to your review" />
            <FilePreviewGrid files={newFiles} onRemove={removeNewFile} onReorder={reorderNewFiles} />
          </div>
          <button
            type="submit"
            disabled={isCreating}
            className={`px-4 py-2.5 rounded-lg bg-primary text-primary-foreground font-semibold text-sm ${
              isCreating ? "cursor-wait opacity-70" : "cursor-pointer hover:opacity-90"
            }`}
          >
            {isCreating ? "Submitting..." : "Submit Review"}
          </button>
        </form>
        {actionError && (
          <p role="alert" className="text-destructive mt-2 text-sm">{actionError}</p>
        )}
      </section>

      <section>
        <h2 className="text-lg font-bold text-foreground mb-3">Student Reviews</h2>
        {isLoading && <p className="text-muted-foreground">Loading reviews...</p>}
        {!isLoading && loadError && (
          <div role="alert" className="text-destructive">
            <p>Could not load reviews: {loadError}</p>
            <button
              type="button"
              className="cursor-pointer mt-1 text-sm font-semibold underline"
              onClick={() => setLoadAttempt((attempt) => attempt + 1)}
            >
              Try again
            </button>
          </div>
        )}
        {!isLoading && !loadError && reviews.length === 0 && (
          <p className="text-muted-foreground">No reviews yet. Be the first to leave one.</p>
        )}
        {!isLoading && !loadError && reviews.map((review) => {
          const isOwnReview = review.user.id === DEV_USER_ID;
          const isEditing = editingReviewId === review.id;
          const isBusy = busyReviewId === review.id;
          const isReordering = reorderingReviewId === review.id;
          const sortedImages = [...review.images].sort((a, b) => a.display_order - b.display_order);

          return (
            <article key={review.id} className="border-b border-border py-5">
              <div className="flex justify-between gap-3 flex-wrap">
                <div>
                  <strong className="text-foreground">{review.user.display_name}</strong>
                  {review.user.affiliation && (
                    <span className="text-muted-foreground ml-2 text-sm">{review.user.affiliation}</span>
                  )}
                  {!isEditing && (
                    <div className="mt-1">
                      <StarPicker value={review.rating} onChange={() => {}} disabled />
                    </div>
                  )}
                </div>
                <small className="text-muted-foreground">
                  {displayDate(review.created_at)}
                  {review.is_edited ? " (edited)" : ""}
                </small>
              </div>

              {isEditing ? (
                <form onSubmit={(event) => handleUpdateReview(event, review)} className="grid gap-3 mt-3">
                  <StarPicker value={editRating} onChange={setEditRating} disabled={isBusy} />
                  <textarea
                    value={editComment}
                    onChange={(event) => setEditComment(event.target.value)}
                    rows={3}
                    className="p-3 rounded-lg border border-border bg-background text-sm resize-y"
                  />

                  {sortedImages.length > 0 && (
                    <div>
                      <label className="block mb-1.5 text-sm text-muted-foreground">
                        Photos — use the arrows to reorder
                      </label>
                      <div className="flex gap-3 flex-wrap">
                        {sortedImages.map((image, index) => (
                          <div key={image.id}>
                            <img
                              src={reviewImageUrl(review.id, image.id)}
                              alt={`Review by ${review.user.display_name}`}
                              loading="lazy"
                              className="w-[90px] h-[68px] object-cover rounded-md border border-border"
                            />
                            <div className="flex justify-center gap-1.5 mt-1">
                              <button
                                type="button"
                                disabled={index === 0 || isBusy || isReordering}
                                className={`text-xs ${
                                  index === 0 || isBusy || isReordering ? "cursor-default opacity-40" : "cursor-pointer"
                                }`}
                                onClick={() => handleReorderReviewImage(review, image.id, "up")}
                              >
                                ←
                              </button>
                              <button
                                type="button"
                                disabled={isBusy || isReordering}
                                className={`text-xs text-destructive ${
                                  isBusy || isReordering ? "cursor-default opacity-40" : "cursor-pointer"
                                }`}
                                onClick={() => handleDeleteReviewImage(review.id, image.id)}
                              >
                                ✕
                              </button>
                              <button
                                type="button"
                                disabled={index === sortedImages.length - 1 || isBusy || isReordering}
                                className={`text-xs ${
                                  index === sortedImages.length - 1 || isBusy || isReordering
                                    ? "cursor-default opacity-40"
                                    : "cursor-pointer"
                                }`}
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
                    <FilePreviewGrid files={editNewFiles} onRemove={removeEditFile} onReorder={reorderEditFiles} />
                  </div>

                  <div className="flex gap-2">
                    <button
                      type="submit"
                      disabled={isBusy}
                      className={`px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-semibold ${
                        isBusy ? "cursor-wait opacity-70" : "cursor-pointer hover:opacity-90"
                      }`}
                    >
                      {isBusy ? "Saving..." : "Save"}
                    </button>
                    <button
                      type="button"
                      disabled={isBusy}
                      className={`px-4 py-2 rounded-lg border border-border text-sm font-semibold ${
                        isBusy ? "cursor-default opacity-70" : "cursor-pointer"
                      }`}
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
                <p className="mt-2 text-foreground">{review.comment || "No written comment."}</p>
              )}

              {!isEditing && sortedImages.length > 0 && (
                <div className="flex gap-3 flex-wrap mt-3">
                  {sortedImages.map((image) => (
                    <img
                      key={image.id}
                      src={reviewImageUrl(review.id, image.id)}
                      alt={`Review by ${review.user.display_name}`}
                      loading="lazy"
                      className="w-[120px] h-[90px] object-cover rounded-lg"
                    />
                  ))}
                </div>
              )}

              {isOwnReview && !isEditing && (
                <div className="flex gap-2 mt-3">
                  <button
                    type="button"
                    disabled={isBusy}
                    className={`px-3 py-1.5 rounded-lg border border-border text-sm font-medium ${
                      isBusy ? "cursor-default opacity-70" : "cursor-pointer hover:bg-muted"
                    }`}
                    onClick={() => beginEditing(review)}
                  >
                    Edit
                  </button>
                  <button
                    type="button"
                    disabled={deletingReviewId === review.id}
                    className={`px-3 py-1.5 rounded-lg border border-destructive/40 text-destructive text-sm font-medium ${
                      deletingReviewId === review.id ? "cursor-default opacity-60" : "cursor-pointer hover:bg-destructive/10"
                    }`}
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
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-card rounded-xl p-6 max-w-sm w-[90%] border border-border shadow-2xl">
            <h3 className="text-lg font-bold text-foreground mb-2">Delete this review?</h3>
            <p className="text-muted-foreground text-sm">
              This action cannot be undone. The review and its photos will be permanently removed.
            </p>
            <div className="flex gap-2.5 justify-end mt-4">
              <button
                type="button"
                disabled={deletingReviewId !== null}
                className={`px-4 py-2 rounded-lg border border-border text-sm font-semibold ${
                  deletingReviewId !== null ? "cursor-default" : "cursor-pointer"
                }`}
                onClick={cancelDeleteReview}
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={deletingReviewId !== null}
                className={`px-4 py-2 rounded-lg bg-destructive text-white text-sm font-semibold ${
                  deletingReviewId !== null ? "cursor-default opacity-60" : "cursor-pointer hover:opacity-90"
                }`}
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