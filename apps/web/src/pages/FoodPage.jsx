import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Bot, Send, X } from "lucide-react";

import { apiUrl } from "../api/client";
import {
  fetchVendorFilters,
  fetchVendorPage,
} from "../api/vendors";

import { askChat, chatErrorMessage } from "../api/chat";

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

  const [searchTerm, setSearchTerm] = useState("");
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
        { role: "bot", text: response.answer },
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
      q: searchTerm,
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
    searchTerm,
    selectedLocation,
    selectedCategory,
    offset,
    loadAttempt,
  ]);

  return (
    <>
      <div
        style={{
          maxWidth: "1000px",
          width: "100%",
          margin: "0 auto",
          padding: "40px 20px",
          fontFamily: "var(--sans)",
          boxSizing: "border-box",
        }}
      >
        <header
          style={{
            marginBottom: "30px",
            textAlign: "center",
          }}
        >
          <h1
            style={{
              color: "var(--text-h)",
              fontFamily: "var(--heading)",
              fontSize: "2.2rem",
            }}
          >
            NTU Foodie Hub
          </h1>

          <p style={{ color: "var(--text)" }}>
            Explore and review food vendors across NTU canteens
          </p>
        </header>

        <div
          style={{
            display: "flex",
            gap: "15px",
            marginBottom: "25px",
            flexWrap: "wrap",
          }}
        >
          <input
            type="text"
            placeholder="Search vendor, location or cuisine..."
            value={searchTerm}
            onChange={(event) => {
              setSearchTerm(event.target.value);
              setOffset(0);
            }}
            style={{
              flex: "1",
              padding: "10px 14px",
              borderRadius: "var(--radius-lg)",
              border: "1px solid var(--border)",
            }}
          />

          <select
            value={selectedLocation}
            onChange={(event) => {
              setSelectedLocation(event.target.value);
              setOffset(0);
            }}
            style={{
              padding: "10px 14px",
              borderRadius: "var(--radius-lg)",
              border: "1px solid var(--border)",
            }}
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
            style={{
              padding: "10px 14px",
              borderRadius: "var(--radius-lg)",
              border: "1px solid var(--border)",
            }}
          >
            <option value="">All categories</option>

            {categories.map((category) => (
              <option key={category} value={category}>
                {category}
              </option>
            ))}
          </select>

          {(searchTerm || selectedLocation || selectedCategory) && (
            <button
              type="button"
              onClick={() => {
                setSearchTerm("");
                setSelectedLocation("");
                setSelectedCategory("");
                setOffset(0);
              }}
            >
              Clear
            </button>
          )}
        </div>

        {isLoading && (
          <p
            style={{
              textAlign: "center",
              color: "var(--text)",
            }}
          >
            Loading vendors...
          </p>
        )}

        {!isLoading && loadError && (
          <div
            role="alert"
            style={{
              textAlign: "center",
              color: "#b91c1c",
            }}
          >
            <p>Could not load vendors: {loadError}</p>

            <button
              type="button"
              onClick={() =>
                setLoadAttempt((attempt) => attempt + 1)
              }
            >
              Try again
            </button>
          </div>
        )}

        {!isLoading &&
          !loadError &&
          vendors.length === 0 && (
            <p
              style={{
                textAlign: "center",
                color: "var(--text)",
              }}
            >
              No vendors found for the selected search or filters.
            </p>
          )}

        {!isLoading &&
          !loadError &&
          vendors.length > 0 && (
            <div
              style={{
                display: "grid",
                gridTemplateColumns:
                  "repeat(auto-fill, minmax(280px, 1fr))",
                gap: "24px",
              }}
            >
              {vendors.map((vendor) => {
                const rating =
                  vendor.average_rating ??
                  vendor.average_google_rating;

                return (
                  <div
                    key={vendor.id}
                    style={{
                      border: "1px solid var(--border)",
                      borderRadius: "var(--radius-lg)",
                      overflow: "hidden",
                      background: "var(--card)",
                      boxShadow: "var(--shadow)",
                      textAlign: "left",
                    }}
                  >
                    {vendor.image_url ? (
                      <img
                        src={apiUrl(vendor.image_url)}
                        alt={vendor.name}
                        style={{
                          width: "100%",
                          height: "160px",
                          objectFit: "cover",
                        }}
                      />
                    ) : (
                      <div
                        role="img"
                        aria-label={`${vendor.name} has no image`}
                        style={{
                          width: "100%",
                          height: "160px",
                          display: "grid",
                          placeItems: "center",
                          background: "var(--code-bg)",
                          color: "var(--text)",
                        }}
                      >
                        No image available
                      </div>
                    )}

                    <div
                      style={{
                        padding: "16px",
                        textAlign: "center",
                      }}
                    >
                      <span
                        style={{
                          fontSize: "0.8rem",
                          color: "var(--accent)",
                          background: "var(--accent-bg)",
                          padding: "4px 10px",
                          borderRadius: "999px",
                        }}
                      >
                        {vendor.location || "NTU"}
                      </span>

                      <h3
                        style={{
                          margin: "10px 0 5px 0",
                          fontFamily: "var(--heading)",
                          color: "var(--text-h)",
                        }}
                      >
                        {vendor.name}
                      </h3>

                      <p
                        style={{
                          margin: "0 0 10px 0",
                          color: "var(--text)",
                          fontSize: "0.9rem",
                        }}
                      >
                        {vendor.category || "Food"}
                        {rating != null
                          ? ` • ⭐ ${rating}`
                          : ""}
                        {` • ${vendor.review_count} reviews`}
                      </p>

                      <Link
                        to={`/food/vendors/${vendor.id}`}
                        style={{
                          display: "inline-block",
                          color: "#fff",
                          background: "var(--accent)",
                          padding: "10px 16px",
                          borderRadius: "var(--radius-lg)",
                          textDecoration: "none",
                          fontSize: "0.9rem",
                          fontWeight: 600,
                        }}
                      >
                        View Reviews
                      </Link>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

        {!isLoading && !loadError && total > 0 && (
  <div className="mt-8 flex items-center justify-center gap-2">
    <button
      type="button"
      disabled={offset === 0}
      onClick={() =>
        setOffset(Math.max(0, offset - PAGE_LIMIT))
      }
      className="rounded-lg border px-4 py-2 disabled:cursor-not-allowed disabled:opacity-40"
    >
      Previous
    </button>

    {Array.from(
      { length: Math.ceil(total / PAGE_LIMIT) },
      (_, index) => {
        const pageNumber = index + 1;
        const currentPage = Math.floor(offset / PAGE_LIMIT) + 1;

        return (
          <button
            key={pageNumber}
            type="button"
            onClick={() =>
              setOffset(index * PAGE_LIMIT)
            }
            className={`h-10 min-w-10 rounded-lg border px-3 ${
              currentPage === pageNumber
                ? "bg-black text-white"
                : "bg-white text-black"
            }`}
          >
            {pageNumber}
          </button>
        );
      },
    )}

    <button
      type="button"
      disabled={offset + PAGE_LIMIT >= total}
      onClick={() => setOffset(offset + PAGE_LIMIT)}
      className="rounded-lg border px-4 py-2 disabled:cursor-not-allowed disabled:opacity-40"
    >
      Next
    </button>
  </div>
)}
      </div>

      {/* FLOATING CHAT WIDGET */}
      <div className="fixed bottom-6 right-6 z-50 flex flex-col items-end gap-3">
        {chatOpen && (
          <div className="w-[360px] rounded-2xl border border-border bg-card shadow-2xl overflow-hidden">
            <div className="flex items-center justify-between px-5 py-4 border-b border-border bg-card">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-full bg-primary flex items-center justify-center flex-shrink-0">
                  <Bot className="w-4 h-4 text-primary-foreground" />
                </div>

                <div>
                  <div className="text-sm font-semibold text-foreground">
                    Foodie
                  </div>

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
                  className={`flex ${
                    msg.role === "user"
                      ? "justify-end"
                      : "justify-start"
                  }`}
                >
                  <div
                    className={`max-w-[82%] px-4 py-2.5 rounded-2xl text-sm leading-relaxed ${
                      msg.role === "user"
                        ? "bg-primary text-primary-foreground rounded-br-sm"
                        : "bg-card border border-border text-foreground rounded-bl-sm"
                    }`}
                  >
                    {msg.text}
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
                          style={{
                            animationDelay: `${i * 0.15}s`,
                          }}
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
                  onChange={(event) =>
                    setChatInput(event.target.value)
                  }
                  onKeyDown={(event) =>
                    event.key === "Enter" &&
                    sendMessage(chatInput)
                  }
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
          onClick={() => setChatOpen((open) => !open)}
          className="flex items-center gap-2.5 px-5 py-3.5 rounded-full bg-primary text-primary-foreground font-semibold text-sm shadow-lg hover:opacity-90 transition-opacity"
          aria-label="Open Foodie chatbot"
        >
          {chatOpen ? (
            <X className="w-4 h-4" />
          ) : (
            <Bot className="w-4 h-4" />
          )}

          {!chatOpen && "Ask Foodie"}
        </button>
      </div>
    </>
  );
}