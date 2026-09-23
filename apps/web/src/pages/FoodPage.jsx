import { useEffect, useState, useRef } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Bot, Send, X } from "lucide-react";

import { apiUrl } from "../api/client";
import { fetchVendorFilters, fetchVendorPage } from "../api/vendors";
import { askChat, chatErrorMessage } from "../api/chat";
import ChatMessageContent from "../components/ChatMessageContent";

const DISPLAY_FONT = "'Fraunces', serif";
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
  const [debouncedSearchTerm, setDebouncedSearchTerm] = useState(urlQuery.trim());
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
        { replace: true }
      );
    }, SEARCH_DEBOUNCE_MS);

    return () => window.clearTimeout(timeoutId);
  }, [searchTerm, setSearchParams]);

  // Load filter dropdown values once
  useEffect(() => {
    const controller = new AbortController();

    fetchVendorFilters(controller.signal)
      .then((filters) => {
        const groupedLocations = [...new Set(filters.locations.map(getLocationGroup))].sort();
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
  }, [debouncedSearchTerm, selectedLocation, selectedCategory, offset, loadAttempt]);

  const hasNextPage = offset + PAGE_LIMIT < total;
  const hasPrevPage = offset > 0;

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
          value={selectedLocation}
          onChange={(event) => {
            setSelectedLocation(event.target.value);
            setOffset(0);
          }}
          className="px-3.5 py-2.5 rounded-xl border border-border bg-background text-foreground"
        >
          <option value="">All locations</option>
          {locations.map((location) => (
            <option key={location} value={location}>
              {location}
            </option>
          ))}
        </select>
        <select
          value={selectedCategory}
          onChange={(event) => {
            setSelectedCategory(event.target.value);
            setOffset(0);
          }}
          className="px-3.5 py-2.5 rounded-xl border border-border bg-background text-foreground"
        >
          <option value="">All categories</option>
          {categories.map((category) => (
            <option key={category} value={category}>
              {category}
            </option>
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
      {!isLoading && !loadError && vendors.length === 0 && (
        <p className="text-center text-muted-foreground">No matching vendors found.</p>
      )}

      {!isLoading && !loadError && vendors.length > 0 && (
        <>
          <div className="grid gap-6" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))" }}>
            {vendors.map((vendor) => {
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

          {(hasPrevPage || hasNextPage) && (
            <div className="flex justify-center gap-3 mt-8">
              <button
                type="button"
                disabled={!hasPrevPage}
                onClick={() => setOffset((prev) => Math.max(0, prev - PAGE_LIMIT))}
                className={`px-4 py-2 rounded-lg border border-border text-sm font-semibold ${
                  hasPrevPage ? "cursor-pointer" : "cursor-default opacity-40"
                }`}
              >
                Previous
              </button>
              <button
                type="button"
                disabled={!hasNextPage}
                onClick={() => setOffset((prev) => prev + PAGE_LIMIT)}
                className={`px-4 py-2 rounded-lg border border-border text-sm font-semibold ${
                  hasNextPage ? "cursor-pointer" : "cursor-default opacity-40"
                }`}
              >
                Next
              </button>
            </div>
          )}
        </>
      )}

      {/* ── FLOATING CHATBOT WIDGET ───────────────────── */}
      <div className="fixed bottom-6 right-6 z-50">
        {chatOpen ? (
          <div className="w-80 sm:w-96 rounded-2xl bg-card border border-border shadow-2xl flex flex-col overflow-hidden transition-all">
            <div className="p-4 bg-primary text-primary-foreground flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Bot className="w-5 h-5" />
                <span className="font-bold text-sm">NTU Foodie Assistant</span>
              </div>
              <button
                onClick={() => setChatOpen(false)}
                className="p-1 hover:bg-black/10 rounded-lg transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-4 h-80 overflow-y-auto flex flex-col gap-3 bg-background">
              {chatMessages.map((msg, idx) => (
                <div
                  key={idx}
                  className={`max-w-[85%] p-3 rounded-xl text-xs leading-relaxed ${
                    msg.role === "user"
                      ? "bg-primary text-primary-foreground self-end rounded-tr-none"
                      : "bg-muted text-foreground self-start rounded-tl-none border border-border"
                  }`}
                >
                  <ChatMessageContent text={msg.text} sources={msg.sources} />
                </div>
              ))}
              {isTyping && (
                <div className="self-start text-xs text-muted-foreground italic">Thinking...</div>
              )}
            </div>

            <form
              onSubmit={(e) => {
                e.preventDefault();
                sendMessage(chatInput);
              }}
              className="p-3 bg-card border-t border-border flex gap-2"
            >
              <input
                type="text"
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                placeholder="Ask about canteens or food..."
                className="flex-1 bg-background text-xs px-3 py-2 rounded-lg border border-border outline-none focus:border-primary/40"
              />
              <button
                type="submit"
                disabled={isTyping}
                className="p-2 rounded-lg bg-primary text-primary-foreground hover:opacity-90 disabled:opacity-50 transition-opacity"
              >
                <Send className="w-4 h-4" />
              </button>
            </form>
          </div>
        ) : (
          <button
            onClick={() => setChatOpen(true)}
            className="p-4 rounded-full bg-primary text-primary-foreground shadow-xl hover:scale-105 transition-transform flex items-center gap-2 font-semibold text-sm"
          >
            <Bot className="w-5 h-5" />
            <span>Ask Foodie</span>
          </button>
        )}
      </div>
    </div>
  );
}