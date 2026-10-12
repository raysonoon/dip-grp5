import { useState } from "react";
import { X } from "lucide-react";

import { saveMyPreferences } from "../api/preferences.js";

const dietaryOptions = [
  "Halal",
  "Vegetarian",
  "Vegan",
  "No pork",
  "No beef",
  "Gluten-free",
  "Dairy-free",
  "Nut allergy",
  "Shellfish allergy",
];

const cuisineOptions = [
  "Chinese",
  "Malay",
  "Indian",
  "Western",
  "Japanese",
  "Korean",
  "Thai",
  "Vegetarian",
];

const locationOptions = [
  "North Spine",
  "South Spine",
  "North Hill",
  "Tanjong Hall",
  "Binjai Hall",
  "The Hive",
  "The Arc",
  "NIE",
  "Gaia",
  "Pioneer Hall",
  "Saraca Hall",
];

const foodPreferenceOptions = [
  "Coffee",
  "Tea",
  "Bubble tea",
  "Protein",
  "Vegetables",
];

const lifestyleOptions = [
  "High protein",
  "High fibre",
];

type Props = {
  onFinished: (status: "completed" | "skipped") => void;
};

function toggleValue(values: string[], value: string) {
  return values.includes(value)
    ? values.filter((item) => item !== value)
    : [...values, value];
}

function Chip({
  label,
  selected,
  onClick,
}: {
  label: string;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-full border px-3 py-2 text-sm transition-colors ${
        selected
          ? "border-primary bg-primary text-primary-foreground"
          : "border-border bg-background text-foreground hover:border-primary/50"
      }`}
    >
      {label}
    </button>
  );
}

export default function FoodPreferencesOnboarding({ onFinished }: Props) {
  const [allergies, setAllergies] = useState<string[]>([]);
  const [cuisines, setCuisines] = useState<string[]>([]);
  const [locations, setLocations] = useState<string[]>([]);
  const [likes, setLikes] = useState<string[]>([]);
  const [dislikes, setDislikes] = useState<string[]>([]);
  const [lifestyle, setLifestyle] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save(status: "completed" | "skipped") {
    setSaving(true);
    setError(null);

    try {
      await saveMyPreferences({
        allergies: status === "completed" ? allergies : [],
        cuisines: status === "completed" ? cuisines : [],
        locations: status === "completed" ? locations : [],
        likes: status === "completed" ? likes : [],
        dislikes: status === "completed" ? dislikes : [],
        lifestyle: status === "completed" ? lifestyle : [],
        onboarding_status: status,
      });

      onFinished(status);
    } catch (saveError) {
      setError(
        saveError instanceof Error
          ? saveError.message
          : "Unable to save preferences",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 px-4 py-8">
      <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-border bg-card shadow-2xl">
        <div className="flex items-start justify-between border-b border-border px-6 py-5">
          <div>
            <h2 className="text-xl font-bold text-foreground">
              Tell us what you like
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Answer five quick questions so Foodie can personalise future
              recommendations.
            </p>
          </div>

          <button
            type="button"
            onClick={() => void save("skipped")}
            disabled={saving}
            className="p-1 text-muted-foreground hover:text-foreground"
            aria-label="Skip preferences"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="space-y-7 px-6 py-6">
          <section>
            <h3 className="mb-3 font-semibold">
              1. Any dietary restrictions or allergies?
            </h3>
            <div className="flex flex-wrap gap-2">
              {dietaryOptions.map((option) => (
                <Chip
                  key={option}
                  label={option}
                  selected={allergies.includes(option)}
                  onClick={() =>
                    setAllergies((current) => toggleValue(current, option))
                  }
                />
              ))}
            </div>
          </section>

          <section>
            <h3 className="mb-3 font-semibold">
              2. Which cuisines do you prefer?
            </h3>
            <div className="flex flex-wrap gap-2">
              {cuisineOptions.map((option) => (
                <Chip
                  key={option}
                  label={option}
                  selected={cuisines.includes(option)}
                  onClick={() =>
                    setCuisines((current) => toggleValue(current, option))
                  }
                />
              ))}
            </div>
          </section>

          <section>
            <h3 className="mb-3 font-semibold">
              3. Which campus locations are most convenient?
            </h3>
            <div className="flex flex-wrap gap-2">
              {locationOptions.map((option) => (
                <Chip
                  key={option}
                  label={option}
                  selected={locations.includes(option)}
                  onClick={() =>
                    setLocations((current) => toggleValue(current, option))
                  }
                />
              ))}
            </div>
          </section>

          <section>
            <h3 className="mb-3 font-semibold">
              4. What do you like or dislike?
            </h3>

            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Like
            </p>
            <div className="mb-4 flex flex-wrap gap-2">
              {foodPreferenceOptions.map((option) => (
                <Chip
                  key={`like-${option}`}
                  label={option}
                  selected={likes.includes(option)}
                  onClick={() => {
                    setLikes((current) => toggleValue(current, option));
                    setDislikes((current) =>
                      current.filter((item) => item !== option),
                    );
                  }}
                />
              ))}
            </div>

            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Prefer less
            </p>
            <div className="flex flex-wrap gap-2">
              {foodPreferenceOptions.map((option) => (
                <Chip
                  key={`dislike-${option}`}
                  label={option}
                  selected={dislikes.includes(option)}
                  onClick={() => {
                    setDislikes((current) => toggleValue(current, option));
                    setLikes((current) =>
                      current.filter((item) => item !== option),
                    );
                  }}
                />
              ))}
            </div>
          </section>

          <section>
            <h3 className="mb-3 font-semibold">
              5. Any lifestyle preferences?
            </h3>
            <div className="flex flex-wrap gap-2">
              {lifestyleOptions.map((option) => (
                <Chip
                  key={option}
                  label={option}
                  selected={lifestyle.includes(option)}
                  onClick={() =>
                    setLifestyle((current) => toggleValue(current, option))
                  }
                />
              ))}
            </div>
          </section>

          {error && (
            <p className="text-sm text-destructive">
              {error}
            </p>
          )}
        </div>

        <div className="flex items-center justify-between border-t border-border px-6 py-5">
          <button
            type="button"
            disabled={saving}
            onClick={() => void save("skipped")}
            className="text-sm font-medium text-muted-foreground hover:text-foreground disabled:opacity-50"
          >
            Skip for now
          </button>

          <button
            type="button"
            disabled={saving}
            onClick={() => void save("completed")}
            className="rounded-xl bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50"
          >
            {saving ? "Saving..." : "Save preferences"}
          </button>
        </div>
      </div>
    </div>
  );
}