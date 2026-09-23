import { useEffect, useState, useRef } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowLeft, Bot, Send, X } from "lucide-react";

import { apiUrl } from "../api/client";
import {
  fetchVendorFilters,
  fetchVendorPage,
} from "../api/vendors";

const DISPLAY_FONT = "'Fraunces', serif";

import { askChat, chatErrorMessage } from "../api/chat";
import ChatMessageContent from "../components/ChatMessageContent";

const SEARCH_DEBOUNCE_MS = 300;

function displayError(error) {
  return error instanceof Error ? error.message : "Something went wrong";
}


function getLocationGroup(location) {
  const value = location.toLowerCase();

  if (value.includes("north spine")) return "North Spine";
  if (value.includes("south spine")) return "South Spine";
  if (value.includes("north hill")) return "North Hill";
  if (value.includes("tanjong hall")) return "Tanjong Hall";
  if (value.includes("binjai hall")) return "Binjai Hall";
  if (value.includes("the hive")) return "The Hive";
  if (value.includes("the arc")) return "The Arc";
  if (value.includes("nie")) return "NIE";
  if (value.includes("gaia")) return "Gaia";
  if (value.includes("pioneer hall")) return "Pioneer Hall";
  if (value.includes("saraca hall")) return "Saraca Hall";
  if (value.includes("hall 11")) return "Hall 11";
  if (value.includes("hall 13")) return "Hall 13";
  if (value.includes("hall 14")) return "Hall 14";
  if (value.includes("hall 16")) return "Hall 16";
  if (value.includes("hall 1")) return "Hall 1";
  if (value.includes("hall 2")) return "Hall 2";
  if (value.includes("hall 4")) return "Hall 4";
  if (value.includes("hall 9")) return "Hall 9";

  return location;
}


export default function FoodPage() {
  const PAGE_LIMIT = 12;

  const [searchParams, setSearchParams] = useSearchParams();
  const urlQuery = searchParams.get("q") ?? "";
  const [searchTerm, setSearchTerm] = useState(urlQuery);
  const [debouncedSearchTerm, setDebouncedSearchTerm] = useState(
    urlQuery.trim(),
  );
  const [selectedLocation, setSelectedLocation] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("");

  const [locations, setLocations] = useState([]);
  const [categories, setCategories] = useState([]);

  const [vendors, setVendors] = useState([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);

  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [loadAttempt, setLoadAttempt] = useState(0);

  // --- CHATBOT STATE ---
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
    setChatMessages((prev) => [
      ...prev,
      { role: "user", text: question },
    ]);
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

  // Keep the input and URL query in sync
  useEffect(() => {
    setSearchTerm(urlQuery);
    setDebouncedSearchTerm(urlQuery.trim());
  }, [urlQuery]);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      const query = searchTerm.trim();
      setDebouncedSearchTerm(query);
      setSearchParams(
        (currentParams) => {
          const nextParams = new URLSearchParams(currentParams);
          if (query) nextParams.set("q", query);
          else nextParams.delete("q");
          return nextParams;
        },
        { replace: true },
      );
    }, SEARCH_DEBOUNCE_MS);

    return () => window.clearTimeout(timeoutId);
  }, [searchTerm, setSearchParams]);

  // Load filter dropdown values once
  useEffect(() => {
    const controller = new AbortController();

    fetchVendorFilters(controller.signal)
      .then((filters) => {
        const groupedLocations = [
          ...new Set(filters.locations.map(getLocationGroup)),
        ].sort();
        setLocations(groupedLocations);
        setCategories(filters.categories);
      })
      .catch((error) => {
        if (error.name !== "AbortError") {
          console.error("Could not load vendor filters", error);
        }
      });

    return () => controller.abort();
  }, []);

  // Load one filtered/paginated vendor page
  useEffect(() => {
    const controller = new AbortController();

    setIsLoading(true);
    setLoadError("");

    fetchVendorPage({
      q: debouncedSearchTerm,
      location: selectedLocation,
      category: selectedCategory,
      limit: PAGE_LIMIT,
      offset,
      signal: controller.signal,
    })
      .then((page) => {
        setVendors(page.items);
        setTotal(page.total);
      })
      .catch((error) => {
        if (error.name !== "AbortError") {
          setLoadError(displayError(error));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setIsLoading(false);
        }
      });

    return () => controller.abort();
  }, [
    debouncedSearchTerm,
    selectedLocation,
    selectedCategory,
    offset,
    loadAttempt,
  ]);

  return (
    <div className="max-w-[1000px] w-full mx-auto px-5 py-10 box-border">
      <header className="mb-8 text-center">
        <h1 className="text-foreground text-3xl font-bold" style={{ fontFamily: DISPLAY_FONT }}>
          NTU Foodie Hub
        </h1>
        <p className="text-muted-foreground">Explore and review food vendors across NTU canteens</p>
      </header>

      <div className="flex gap-4 mb-6 flex-wrap">
        <input
          type="text"
          placeholder="Search vendor or cuisine..."
          value={searchTerm}
          onChange={(event) => setSearchTerm(event.target.value)}
          className="flex-1 px-3.5 py-2.5 rounded-xl border border-border bg-background text-foreground"
        />
        <select
          value={selectedCanteen}
          onChange={(event) => setSelectedCanteen(event.target.value)}
          className="px-3.5 py-2.5 rounded-xl border border-border bg-background text-foreground"
        >
          {canteens.map((canteen) => (
            <option key={canteen} value={canteen}>{canteen}</option>
          ))}
        </select>
      </div>

      {isLoading && <p className="text-center text-muted-foreground">Loading vendors...</p>}
      {!isLoading && loadError && (
        <div role="alert" className="text-center text-destructive">
          <p>Could not load vendors: {loadError}</p>
          <button
            type="button"
            className="cursor-pointer mt-2 underline text-sm font-semibold"
            onClick={() => setLoadAttempt((attempt) => attempt + 1)}
          >
            Try again
          </button>
        </div>
      )}
      {!isLoading && !loadError && filteredVendors.length === 0 && (
        <p className="text-center text-muted-foreground">No matching vendors found.</p>
      )}

      {!isLoading && !loadError && (
        <div className="grid gap-6" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))" }}>
          {filteredVendors.map((vendor) => {
            const rating = vendor.average_rating ?? vendor.average_google_rating;
            return (
              <div
                key={vendor.id}
                className="border border-border rounded-xl overflow-hidden bg-card shadow-sm text-left"
              >
                {vendor.image_url ? (
                  <img
                    src={apiUrl(vendor.image_url)}
                    alt={vendor.name}
                    className="w-full h-40 object-cover"
                  />
                ) : (
                  <div
                    role="img"
                    aria-label={`${vendor.name} has no image`}
                    className="w-full h-40 grid place-items-center bg-muted text-muted-foreground"
                  >
                    No image available
                  </div>
                )}
                <div className="p-4 text-center">
                  <span className="text-xs text-primary bg-primary/10 px-2.5 py-1 rounded-full">
                    {vendor.location || "NTU"}
                  </span>
                  <h3
                    className="mt-2.5 mb-1 text-foreground font-bold"
                    style={{ fontFamily: DISPLAY_FONT }}
                  >
                    {vendor.name}
                  </h3>
                  <p className="mb-2.5 text-muted-foreground text-sm">
                    {vendor.category || "Food"}
                    {rating != null ? ` • ⭐ ${rating}` : ""}
                    {` • ${vendor.review_count} reviews`}
                  </p>
                  <Link
                    to={`/food/vendors/${vendor.id}`}
                    className="inline-block text-white bg-primary px-4 py-2.5 rounded-xl text-sm font-semibold hover:opacity-90 transition-opacity no-underline"
                  >
                    View Reviews
                  </Link>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}