import { useEffect, useState, useRef } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowLeft, Bot, Send, X } from "lucide-react";

import { apiUrl } from "../api/client";
import { fetchVendors } from "../api/vendors";

// TODO: Update these imports to point to your actual chat API functions
import { askChat, chatErrorMessage } from "../api/chat";
import ChatMessageContent from "../components/ChatMessageContent";

const SEARCH_DEBOUNCE_MS = 300;

function displayError(error) {
  return error instanceof Error ? error.message : "Something went wrong";
}

export default function FoodPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const urlQuery = searchParams.get("q") ?? "";
  const [searchTerm, setSearchTerm] = useState(urlQuery);
  const [debouncedSearchTerm, setDebouncedSearchTerm] = useState(
    urlQuery.trim(),
  );
  const [selectedCanteen, setSelectedCanteen] = useState("All");
  const [vendors, setVendors] = useState([]);
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
  // ---------------------

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

  useEffect(() => {
    const controller = new AbortController();
    setIsLoading(true);
    setLoadError("");

    fetchVendors(debouncedSearchTerm, controller.signal)
      .then(setVendors)
      .catch((error) => {
        if (error.name !== "AbortError") setLoadError(displayError(error));
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsLoading(false);
      });

    return () => controller.abort();
  }, [debouncedSearchTerm, loadAttempt]);

  const canteens = [
    "All",
    ...new Set(vendors.map((vendor) => vendor.location).filter(Boolean)),
  ];
  const filteredVendors = vendors.filter((vendor) => {
    const matchesCanteen =
      selectedCanteen === "All" || vendor.location === selectedCanteen;
    return matchesCanteen;
  });

  return (
    <>
      <div style={{ maxWidth: "1000px", width: "100%", margin: "0 auto", padding: "40px 20px", fontFamily: "var(--sans)", boxSizing: "border-box" }}>
        <header style={{ marginBottom: "30px", textAlign: "center" }}>
          <div style={{ display: "flex", justifyContent: "flex-start", marginBottom: "20px" }}>
            <Link
              to="/"
              aria-label="Back to homepage"
              style={{ display: "inline-flex", alignItems: "center", gap: "8px", color: "#fff", background: "var(--accent)", padding: "10px 16px", borderRadius: "var(--radius-lg)", textDecoration: "none", fontSize: "0.9rem", fontWeight: 600 }}
            >
              <ArrowLeft size={17} aria-hidden="true" />
              Back to homepage
            </Link>
          </div>
          <h1 style={{ color: "var(--text-h)", fontFamily: "var(--heading)", fontSize: "2.2rem" }}>NTU Foodie Hub</h1>
          <p style={{ color: "var(--text)" }}>Explore and review food vendors across NTU canteens</p>
        </header>

        <div style={{ display: "flex", gap: "15px", marginBottom: "25px", flexWrap: "wrap" }}>
          <input
            type="text"
            placeholder="Search vendor or cuisine..."
            value={searchTerm}
            onChange={(event) => setSearchTerm(event.target.value)}
            style={{ flex: "1", padding: "10px 14px", borderRadius: "var(--radius-lg)", border: "1px solid var(--border)" }}
          />
          <select
            value={selectedCanteen}
            onChange={(event) => setSelectedCanteen(event.target.value)}
            style={{ padding: "10px 14px", borderRadius: "var(--radius-lg)", border: "1px solid var(--border)" }}
          >
            {canteens.map((canteen) => (
              <option key={canteen} value={canteen}>{canteen}</option>
            ))}
          </select>
        </div>

        {isLoading && <p style={{ textAlign: "center", color: "var(--text)" }}>Loading vendors...</p>}
        {!isLoading && loadError && (
          <div role="alert" style={{ textAlign: "center", color: "#b91c1c" }}>
            <p>Could not load vendors: {loadError}</p>
            <button type="button" onClick={() => setLoadAttempt((attempt) => attempt + 1)}>Try again</button>
          </div>
        )}
        {!isLoading && !loadError && filteredVendors.length === 0 && (
          <p style={{ textAlign: "center", color: "var(--text)" }}>No matching vendors found.</p>
        )}

        {!isLoading && !loadError && (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: "24px" }}>
            {filteredVendors.map((vendor) => {
              const rating = vendor.average_rating ?? vendor.average_google_rating;
              return (
                <div
                  key={vendor.id}
                  style={{ border: "1px solid var(--border)", borderRadius: "var(--radius-lg)", overflow: "hidden", background: "var(--card)", boxShadow: "var(--shadow)", textAlign: "left" }}
                >
                  {vendor.image_url ? (
                    <img src={apiUrl(vendor.image_url)} alt={vendor.name} style={{ width: "100%", height: "160px", objectFit: "cover" }} />
                  ) : (
                    <div role="img" aria-label={`${vendor.name} has no image`} style={{ width: "100%", height: "160px", display: "grid", placeItems: "center", background: "var(--code-bg)", color: "var(--text)" }}>No image available</div>
                  )}
                  <div style={{ padding: "16px", textAlign: "center" }}>
                    <span style={{ fontSize: "0.8rem", color: "var(--accent)", background: "var(--accent-bg)", padding: "4px 10px", borderRadius: "999px" }}>
                      {vendor.location || "NTU"}
                    </span>
                    <h3 style={{ margin: "10px 0 5px 0", fontFamily: "var(--heading)", color: "var(--text-h)" }}>{vendor.name}</h3>
                    <p style={{ margin: "0 0 10px 0", color: "var(--text)", fontSize: "0.9rem" }}>
                      {vendor.category || "Food"}
                      {rating != null ? ` • ⭐ ${rating}` : ""}
                      {` • ${vendor.review_count} reviews`}
                    </p>
                    <Link
                      to={`/food/vendors/${vendor.id}`}
                      style={{ display: "inline-block", color: "#fff", background: "var(--accent)", padding: "10px 16px", borderRadius: "var(--radius-lg)", textDecoration: "none", fontSize: "0.9rem", fontWeight: 600 }}
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

      {/* ── FLOATING CHAT WIDGET ─────────────────────── */}
      <div className="fixed bottom-6 right-6 z-50 flex flex-col items-end gap-3">
        {/* Chat popover */}
        {chatOpen && (
          <div className="w-[360px] rounded-2xl border border-border bg-card shadow-2xl overflow-hidden">
            {/* Header */}
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

            {/* Messages */}
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

            {/* Input area */}
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

        {/* Toggle button */}
        <button
          type="button"
          onClick={() => setChatOpen((o) => !o)}
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
