import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Heart } from "lucide-react";

import {
  favouriteVendor,
  fetchVendorFavourite,
  unfavouriteVendor,
} from "../api/favourites.js";
import { useAuth } from "../contexts/AuthContext";


export default function VendorFavouriteButton({ vendorId }: { vendorId: number }) {
  const { user, loading: authLoading } = useAuth();
  const userId = user?.id;
  const [favourited, setFavourited] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (authLoading || !userId) return undefined;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    fetchVendorFavourite(vendorId, controller.signal)
      .then((state) => {
        if (!controller.signal.aborted) setFavourited(state.favourited);
      })
      .catch(() => {
        if (!controller.signal.aborted) setError("Unable to load your favourite status. Please try again.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [authLoading, userId, vendorId, attempt]);

  async function toggleFavourite() {
    if (favourited === null) {
      setAttempt((current) => current + 1);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      if (favourited) await unfavouriteVendor(vendorId);
      else await favouriteVendor(vendorId);
      setFavourited(!favourited);
    } catch {
      setError("Unable to update your favourites. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  if (!authLoading && !user) {
    return (
      <p className="mt-4 text-sm text-muted-foreground">
        <Link
          to="/signin"
          state={{ from: `/vendors/${vendorId}` }}
          className="font-semibold text-primary hover:underline"
        >
          Sign in or sign up
        </Link>{" "}
        to save this place to your favourites.
      </p>
    );
  }

  return (
    <div className="mt-4">
      <button
        type="button"
        aria-pressed={favourited ?? false}
        disabled={authLoading || loading || saving}
        onClick={() => void toggleFavourite()}
        className={`inline-flex items-center gap-2 rounded-lg border px-4 py-2 text-sm font-semibold transition-colors disabled:cursor-wait disabled:opacity-60 ${
          favourited ? "border-primary bg-primary/10 text-primary" : "border-border text-foreground hover:bg-muted"
        }`}
      >
        <Heart aria-hidden="true" className={`h-4 w-4 ${favourited ? "fill-current" : ""}`} />
        {authLoading || loading ? "Loading favourites..." : saving ? "Saving..." : favourited === null ? "Retry favourite status" : favourited ? "Remove from favourites" : "Add to favourites"}
      </button>
      {error && <p role="alert" className="mt-2 text-sm text-destructive">{error}</p>}
    </div>
  );
}
