import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ChevronLeft, ChevronRight } from "lucide-react";

import { fetchMyFavourites } from "../api/favourites.js";

type Favourite = { vendor: { id: number; name: string }; created_at: string };
type FavouritesPage = { items: Favourite[]; total: number; offset: number };
const PAGE_SIZE = 5;

export default function FavouritePlaces() {
  const [page, setPage] = useState<FavouritesPage>({ items: [], total: 0, offset: 0 });
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(false);
    fetchMyFavourites({ limit: PAGE_SIZE, offset, signal: controller.signal })
      .then((result) => {
        if (controller.signal.aborted) return;
        // Another tab may have removed the final item on the last page.
        if (result.total > 0 && offset >= result.total) {
          setOffset(Math.floor((result.total - 1) / PAGE_SIZE) * PAGE_SIZE);
          return;
        }
        setPage(result);
      })
      .catch(() => {
        if (!controller.signal.aborted) setError(true);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [offset, attempt]);

  if (loading) return <p role="status" className="text-sm text-muted-foreground">Loading your favourites...</p>;
  if (error) {
    return (
      <div>
        <p role="alert" className="text-sm text-destructive">Unable to load your favourites. Please try again.</p>
        <button type="button" onClick={() => setAttempt((current) => current + 1)} className="mt-2 text-sm font-semibold text-primary hover:underline">Try again</button>
      </div>
    );
  }
  if (!page.items.length) return <p className="text-sm text-muted-foreground">No favourites found</p>;

  return (
    <>
      <ul className="divide-y divide-border">
        {page.items.map((favourite) => (
          <li key={favourite.vendor.id} className="py-3 first:pt-0 last:pb-0">
            <Link to={`/vendors/${favourite.vendor.id}`} className="font-semibold text-foreground hover:text-primary">
              {favourite.vendor.name}
            </Link>
            <p className="mt-1 text-xs text-muted-foreground">
              Saved {new Date(favourite.created_at).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })}
            </p>
          </li>
        ))}
      </ul>
      {page.total > PAGE_SIZE && (
        <div className="mt-4 flex items-center justify-between gap-3 border-t border-border pt-4">
          <p className="text-xs text-muted-foreground">Showing {page.offset + 1}–{page.offset + page.items.length} of {page.total}</p>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={offset === 0}
              onClick={() => setOffset((current) => Math.max(0, current - PAGE_SIZE))}
              className="inline-flex items-center gap-1 rounded-lg border border-border px-3 py-1.5 text-sm font-medium text-foreground transition-colors hover:bg-muted disabled:cursor-not-allowed disabled:opacity-50"
            >
              <ChevronLeft aria-hidden="true" className="h-4 w-4" />Previous
            </button>
            <button
              type="button"
              disabled={offset + PAGE_SIZE >= page.total}
              onClick={() => setOffset((current) => current + PAGE_SIZE)}
              className="inline-flex items-center gap-1 rounded-lg border border-border px-3 py-1.5 text-sm font-medium text-foreground transition-colors hover:bg-muted disabled:cursor-not-allowed disabled:opacity-50"
            >
              Next<ChevronRight aria-hidden="true" className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}
    </>
  );
}
