import { useEffect, useState, type ReactNode } from "react";
import { Link, Navigate } from "react-router-dom";
import {
  ChevronLeft,
  ChevronRight,
  Heart,
  MessageSquare,
  Pencil,
  Star,
  Utensils,
} from "lucide-react";

import { fetchMyReviews } from "../api/account.js";
import { fetchMyPreferences, saveMyPreferences } from "../api/preferences.js";
import {
  Chip,
  cuisineOptions,
  dietaryOptions,
  foodPreferenceOptions,
  lifestyleOptions,
  locationOptions,
  toggleValue,
} from "../components/FoodPreferencesOnboarding";
import { useAuth } from "../contexts/AuthContext";

type PreferenceKey =
  | "allergies"
  | "cuisines"
  | "locations"
  | "likes"
  | "dislikes"
  | "lifestyle";

type FoodPreferences = Record<PreferenceKey, string[]> & {
  onboarding_status: string;
};

type RecentReview = {
  id: number;
  rating: number;
  comment: string | null;
  created_at: string;
  vendor: { id: number; name: string };
};

type ReviewsPage = { items: RecentReview[]; total: number };

const REVIEWS_PAGE_SIZE = 5;

const PREFERENCE_FIELDS: { key: PreferenceKey; label: string; options: string[] }[] = [
  { key: "allergies", label: "Allergies & dietary restrictions", options: dietaryOptions },
  { key: "cuisines", label: "Cuisines", options: cuisineOptions },
  { key: "locations", label: "Locations", options: locationOptions },
  { key: "likes", label: "Likes", options: foodPreferenceOptions },
  { key: "dislikes", label: "Dislikes", options: foodPreferenceOptions },
  { key: "lifestyle", label: "Lifestyle", options: lifestyleOptions },
];

const EMPTY_PREFERENCES: Record<PreferenceKey, string[]> = {
  allergies: [],
  cuisines: [],
  locations: [],
  likes: [],
  dislikes: [],
  lifestyle: [],
};

function pickPreferences(
  preferences: FoodPreferences | null,
): Record<PreferenceKey, string[]> {
  if (!preferences) return { ...EMPTY_PREFERENCES };
  return {
    allergies: preferences.allergies ?? [],
    cuisines: preferences.cuisines ?? [],
    locations: preferences.locations ?? [],
    likes: preferences.likes ?? [],
    dislikes: preferences.dislikes ?? [],
    lifestyle: preferences.lifestyle ?? [],
  };
}

function formatDate(value: string) {
  return new Date(value).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

function Section({
  icon,
  title,
  action,
  children,
}: {
  icon: ReactNode;
  title: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-border bg-card p-6">
      <div className="mb-4 flex items-center justify-between gap-4">
        <h2 className="flex items-center gap-2 text-lg font-bold text-foreground">
          {icon}
          {title}
        </h2>
        {action}
      </div>
      {children}
    </section>
  );
}

export default function AccountPage() {
  const { loading: authLoading, session, user } = useAuth();
  const userId = session?.user.id ?? null;

  const [preferences, setPreferences] = useState<FoodPreferences | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [reviewsPage, setReviewsPage] = useState<ReviewsPage>({ items: [], total: 0 });
  const [reviewOffset, setReviewOffset] = useState(0);
  const [reviewsLoading, setReviewsLoading] = useState(true);
  const [reviewsError, setReviewsError] = useState<string | null>(null);

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Record<PreferenceKey, string[]>>(EMPTY_PREFERENCES);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    if (!userId) return undefined;
    let active = true;

    async function load() {
      setLoading(true);
      setLoadError(null);
      try {
        const savedPreferences = await fetchMyPreferences();
        if (!active) return;
        setPreferences(savedPreferences);
      } catch (error) {
        if (!active) return;
        console.error("Unable to load account", error);
        setLoadError("Unable to load your account. Please try again.");
      } finally {
        if (active) setLoading(false);
      }
    }

    void load();
    return () => {
      active = false;
    };
  }, [userId]);

  useEffect(() => {
    if (!userId) return undefined;
    let active = true;

    async function loadReviews() {
      setReviewsLoading(true);
      setReviewsError(null);
      try {
        const page = await fetchMyReviews({
          limit: REVIEWS_PAGE_SIZE,
          offset: reviewOffset,
        });
        if (!active) return;
        setReviewsPage({ items: page.items ?? [], total: page.total ?? 0 });
      } catch (error) {
        if (!active) return;
        console.error("Unable to load reviews", error);
        setReviewsError("Unable to load your reviews. Please try again.");
      } finally {
        if (active) setReviewsLoading(false);
      }
    }

    void loadReviews();
    return () => {
      active = false;
    };
  }, [userId, reviewOffset]);

  if (authLoading) {
    return <p className="px-6 py-10 text-center text-muted-foreground">Loading...</p>;
  }

  if (!session) {
    return <Navigate to="/signin" replace state={{ from: "/account" }} />;
  }

  function startEditing() {
    setDraft(pickPreferences(preferences));
    setSaveError(null);
    setEditing(true);
  }

  function toggleDraft(key: PreferenceKey, option: string) {
    setDraft((current) => {
      const next = { ...current, [key]: toggleValue(current[key], option) };
      // An item can be liked or disliked, not both.
      if (key === "likes") next.dislikes = next.dislikes.filter((item) => item !== option);
      if (key === "dislikes") next.likes = next.likes.filter((item) => item !== option);
      return next;
    });
  }

  async function savePreferences() {
    setSaving(true);
    setSaveError(null);
    try {
      const saved = await saveMyPreferences({
        ...draft,
        onboarding_status: "completed",
      });
      setPreferences(saved);
      setEditing(false);
    } catch (error) {
      setSaveError(
        error instanceof Error ? error.message : "Unable to save preferences",
      );
    } finally {
      setSaving(false);
    }
  }

  const savedPreferences = pickPreferences(preferences);

  return (
    <div className="mx-auto max-w-3xl space-y-6 px-6 py-10">
      <div>
        <h1 className="font-display text-2xl font-bold text-foreground">Account</h1>
        <p className="mt-1 text-sm text-muted-foreground">{user?.email}</p>
      </div>

      {loading ? (
        <p className="text-muted-foreground">Loading your account...</p>
      ) : loadError ? (
        <p className="text-sm text-destructive">{loadError}</p>
      ) : (
        <>
          <Section
            icon={<Utensils className="h-5 w-5 text-primary" />}
            title="Food preferences"
            action={
              !editing && (
                <button
                  type="button"
                  onClick={startEditing}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-sm font-medium text-foreground transition-colors hover:bg-muted"
                >
                  <Pencil className="h-4 w-4" />
                  Edit
                </button>
              )
            }
          >
            {editing ? (
              <div className="space-y-5">
                {PREFERENCE_FIELDS.map(({ key, label, options }) => {
                  // Keep any saved values that are no longer in the option list.
                  const choices = [
                    ...options,
                    ...draft[key].filter((value) => !options.includes(value)),
                  ];
                  return (
                    <div key={key}>
                      <h3 className="mb-2 text-sm font-semibold text-foreground">{label}</h3>
                      <div className="flex flex-wrap gap-2">
                        {choices.map((option) => (
                          <Chip
                            key={option}
                            label={option}
                            selected={draft[key].includes(option)}
                            onClick={() => toggleDraft(key, option)}
                          />
                        ))}
                      </div>
                    </div>
                  );
                })}

                {saveError && <p className="text-sm text-destructive">{saveError}</p>}

                <div className="flex justify-end gap-2 border-t border-border pt-4">
                  <button
                    type="button"
                    disabled={saving}
                    onClick={() => setEditing(false)}
                    className="rounded-lg px-4 py-2 text-sm font-medium text-muted-foreground hover:text-foreground disabled:opacity-50"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    disabled={saving}
                    onClick={() => void savePreferences()}
                    className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50"
                  >
                    {saving ? "Saving..." : "Save preferences"}
                  </button>
                </div>
              </div>
            ) : (
              <>
                {!preferences && (
                  <p className="mb-4 text-sm text-muted-foreground">
                    You haven't set your food preferences yet.
                  </p>
                )}
                <dl className="grid gap-4 sm:grid-cols-2">
                  {PREFERENCE_FIELDS.map(({ key, label }) => (
                    <div key={key}>
                      <dt className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                        {label}
                      </dt>
                      <dd className="flex flex-wrap gap-1.5">
                        {savedPreferences[key].length ? (
                          savedPreferences[key].map((value) => (
                            <span
                              key={value}
                              className="rounded-full bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary"
                            >
                              {value}
                            </span>
                          ))
                        ) : (
                          <span className="text-sm text-muted-foreground">None</span>
                        )}
                      </dd>
                    </div>
                  ))}
                </dl>
              </>
            )}
          </Section>

          <Section icon={<Heart className="h-5 w-5 text-primary" />} title="Favourite places">
            <p className="text-sm text-muted-foreground">No favourites found</p>
          </Section>

          <Section
            icon={<MessageSquare className="h-5 w-5 text-primary" />}
            title="Recently reviewed places"
          >
            {reviewsError ? (
              <p className="text-sm text-destructive">{reviewsError}</p>
            ) : reviewsLoading && !reviewsPage.items.length ? (
              <p className="text-sm text-muted-foreground">Loading your reviews...</p>
            ) : reviewsPage.items.length ? (
              <>
                <ul className="divide-y divide-border">
                  {reviewsPage.items.map((review) => (
                    <li key={review.id} className="py-3 first:pt-0 last:pb-0">
                      <div className="flex items-center justify-between gap-3">
                        <Link
                          to={`/vendors/${review.vendor.id}`}
                          className="font-semibold text-foreground hover:text-primary"
                        >
                          {review.vendor.name}
                        </Link>
                        <span className="flex shrink-0 items-center gap-1 text-sm font-semibold text-foreground">
                          <Star className="h-4 w-4 fill-amber-400 text-amber-400" />
                          {review.rating.toFixed(1)}
                        </span>
                      </div>
                      <p className="mt-1 text-sm text-muted-foreground">
                        {review.comment || <span className="italic">No comment</span>}
                      </p>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {formatDate(review.created_at)}
                      </p>
                    </li>
                  ))}
                </ul>

                {reviewsPage.total > REVIEWS_PAGE_SIZE && (
                  <div className="mt-4 flex items-center justify-between gap-3 border-t border-border pt-4">
                    <p className="text-xs text-muted-foreground">
                      Showing {reviewOffset + 1}–{reviewOffset + reviewsPage.items.length} of{" "}
                      {reviewsPage.total}
                    </p>
                    <div className="flex gap-2">
                      <button
                        type="button"
                        disabled={reviewsLoading || reviewOffset === 0}
                        onClick={() =>
                          setReviewOffset((current) => Math.max(0, current - REVIEWS_PAGE_SIZE))
                        }
                        className="inline-flex items-center gap-1 rounded-lg border border-border px-3 py-1.5 text-sm font-medium text-foreground transition-colors hover:bg-muted disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        <ChevronLeft className="h-4 w-4" />
                        Previous
                      </button>
                      <button
                        type="button"
                        disabled={
                          reviewsLoading || reviewOffset + REVIEWS_PAGE_SIZE >= reviewsPage.total
                        }
                        onClick={() => setReviewOffset((current) => current + REVIEWS_PAGE_SIZE)}
                        className="inline-flex items-center gap-1 rounded-lg border border-border px-3 py-1.5 text-sm font-medium text-foreground transition-colors hover:bg-muted disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        Next
                        <ChevronRight className="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                )}
              </>
            ) : (
              <p className="text-sm text-muted-foreground">
                You haven't reviewed any places yet.
              </p>
            )}
          </Section>
        </>
      )}
    </div>
  );
}
