import { useRef, useState } from "react";
import { Routes, Route, Link } from "react-router-dom";
import { askChat, chatErrorMessage } from "./api/chat";
import FoodPage from "./pages/FoodPage";
import VendorsPage from "./pages/VendorsPage";
// @ts-ignore
import VendorMap from "./pages/VendorMap";
import {
  Search,
  Star,
  MapPin,
  Bot,
  Send,
  ChevronRight,
  Clock,
  Utensils,
  TrendingUp,
  Menu,
  X,
  ThumbsUp,
} from "lucide-react";

const DISPLAY_FONT = "'Fraunces', serif";
const BODY_FONT = "'Plus Jakarta Sans', sans-serif";

const STALLS = [
  {
    id: 1,
    name: "Uncle Lim's Chicken Rice",
    canteen: "North Spine Food Court",
    cuisine: "Chinese",
    rating: 4.7,
    reviews: 312,
    price: "$3.50–$5",
    image:
      "https://images.unsplash.com/photo-1602253057119-44d745d9b860?w=400&h=280&fit=crop&auto=format",
    tags: ["Chicken Rice", "Roast"],
    topReview:
      "The roast chicken is absolutely tender and the chilli sauce hits different!",
  },
  {
    id: 2,
    name: "Ah Kow Ramen Bar",
    canteen: "The Hive",
    cuisine: "Japanese",
    rating: 4.5,
    reviews: 187,
    price: "$7–$10",
    image:
      "https://images.unsplash.com/photo-1612927601601-6638404737ce?w=400&h=280&fit=crop&auto=format",
    tags: ["Ramen", "Tonkotsu"],
    topReview:
      "Rich broth and perfectly done soft-boiled eggs. Go early to skip the queue!",
  },
  {
    id: 3,
    name: "Mama's Ban Mian",
    canteen: "Pioneer Canteen",
    cuisine: "Chinese",
    rating: 4.8,
    reviews: 429,
    price: "$4–$6",
    image:
      "https://images.unsplash.com/photo-1681038560284-58214f7ea0ac?w=400&h=280&fit=crop&auto=format",
    tags: ["Ban Mian", "Soup"],
    topReview:
      "Best ban mian on campus. Handmade noodles and crispy ikan bilis — perfection.",
  },
  {
    id: 4,
    name: "Seoulmate Korean Kitchen",
    canteen: "Foodgle Hub",
    cuisine: "Korean",
    rating: 4.4,
    reviews: 204,
    price: "$8–$12",
    image:
      "https://images.unsplash.com/photo-1526318896980-cf78c088247c?w=400&h=280&fit=crop&auto=format",
    tags: ["Bibimbap", "Kimchi Jjigae"],
    topReview:
      "Portions are generous and the kimchi jjigae is genuinely authentic. Great value.",
  },
];

const REVIEWS = [
  {
    id: 1,
    initials: "W",
    user: "Wei Ling T.",
    programme: "Computer Science, Yr 3",
    stall: "Uncle Lim's Chicken Rice",
    canteen: "North Spine",
    rating: 5,
    date: "2 days ago",
    text: "Been eating here every week since Year 1. The soya sauce chicken is unmatched — silky smooth and the rice is always fluffy. Uncle and Auntie are so friendly too!",
    helpful: 47,
  },
  {
    id: 2,
    initials: "A",
    user: "Arjun M.",
    programme: "Electrical Engineering, Yr 2",
    stall: "Mama's Ban Mian",
    canteen: "Pioneer Canteen",
    rating: 5,
    date: "5 days ago",
    text: "Stumbled here before a 9am lab. The dry ban mian with extra egg is my go-to fuel now. Queue moves fast despite looking long. 100% recommend over the usual suspects.",
    helpful: 33,
  },
  {
    id: 3,
    initials: "S",
    user: "Sarah K.",
    programme: "Business, Yr 4",
    stall: "Ah Kow Ramen Bar",
    canteen: "The Hive",
    rating: 4,
    date: "1 week ago",
    text: "For campus ramen this is genuinely impressive. The shoyu broth surprised me. A bit pricier than other options but worth it as an occasional treat between tutorials.",
    helpful: 29,
  },
];

const SUGGESTED_QUESTIONS = [
  "What's cheap near North Spine?",
  "Best mala on campus?",
  "What's open after 8pm?",
];

function StarRow({ rating, size = "sm" }: { rating: number; size?: "sm" | "md" }) {
  return (
    <div className="flex items-center gap-0.5">
      {[1, 2, 3, 4, 5].map((i) => (
        <Star
          key={i}
          className={`${size === "sm" ? "w-3.5 h-3.5" : "w-4 h-4"} ${
            i <= Math.round(rating)
              ? "fill-primary text-primary"
              : "fill-transparent text-muted"
          }`}
        />
      ))}
    </div>
  );
}

function HomePage() {
  const [searchQuery, setSearchQuery] = useState("");
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [chatMessages, setChatMessages] = useState<
    { role: "user" | "bot"; text: string }[]
  >([
    {
      role: "bot",
      text: "Hey there! I'm Foodie, your NTU campus food guide 🍜 Ask me about canteens, opening hours, or what's good today!",
    },
  ]);
  const [chatInput, setChatInput] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const chatRequestPending = useRef(false);

  async function sendMessage(text: string) {
    const question = text.trim();
    if (!question || chatRequestPending.current) return;

    chatRequestPending.current = true;
    setChatMessages((prev) => [...prev, { role: "user", text: question }]);
    setChatInput("");
    setIsTyping(true);

    try {
      const response = await askChat(question);
      setChatMessages((prev) => [...prev, { role: "bot", text: response.answer }]);
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

  return (
    <div
      className="min-h-screen bg-background text-foreground overflow-x-hidden"
      style={{ fontFamily: BODY_FONT }}
    >
      {/* ── NAV ──────────────────────────────────────── */}
      <nav className="fixed top-0 left-0 right-0 z-50 border-b border-border bg-background/80 backdrop-blur-md">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center">
              <Utensils className="w-4 h-4 text-primary-foreground" />
            </div>
            <span
              className="text-lg font-bold text-foreground"
              style={{ fontFamily: DISPLAY_FONT }}
            >
              NTU Foodie Guide
            </span>
          </div>

          <div className="hidden md:flex items-center gap-3">
            <button className="text-sm text-muted-foreground hover:text-foreground transition-colors">
              Sign In
            </button>
            <Link
              to="/map"
              className="text-sm px-4 py-2 rounded-lg border border-border text-foreground font-semibold hover:bg-muted transition-colors"
            >
              Map
            </Link>
            <Link
              to="/food"
              className="text-sm px-4 py-2 rounded-lg bg-primary text-primary-foreground font-semibold hover:opacity-90 transition-opacity"
            >
              Discover
            </Link>
          </div>

          <button
            className="md:hidden text-muted-foreground p-1"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            aria-label="Toggle menu"
          >
            {mobileMenuOpen ? (
              <X className="w-5 h-5" />
            ) : (
              <Menu className="w-5 h-5" />
            )}
          </button>
        </div>

        {mobileMenuOpen && (
          <div className="md:hidden border-t border-border bg-background px-6 py-4 flex flex-col gap-4 text-sm">
            {["Discover", "Map"].map((link) =>
              link === "Discover" ? (
                <Link
                  key={link}
                  to="/food"
                  className="text-muted-foreground hover:text-foreground transition-colors"
                >
                  {link}
                </Link>
              ) : (
                <Link
                  key={link}
                  to="/map"
                  className="text-muted-foreground hover:text-foreground transition-colors"
                >
                  {link}
                </Link>
              )
            )}
            <button className="w-full py-2.5 rounded-lg bg-primary text-primary-foreground font-semibold">
              Leave a Review
            </button>
          </div>
        )}
      </nav>

      {/* ── HERO ─────────────────────────────────────── */}
      <section className="relative min-h-screen flex items-center pt-16">
        <div
          className="absolute inset-0 bg-cover bg-center bg-no-repeat bg-muted"
          style={{
            backgroundImage:
              "url('https://images.unsplash.com/photo-1628532429788-c35922b5e6c1?w=1600&h=900&fit=crop&auto=format')",
          }}
        />
        <div className="absolute inset-0 bg-gradient-to-r from-background/96 via-background/84 to-background/20" />
        <div className="absolute inset-0 bg-gradient-to-t from-background/50 via-transparent to-transparent" />

        <div className="relative z-10 max-w-7xl mx-auto px-6 py-28">
          <div className="max-w-2xl">
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-primary/30 bg-primary/10 text-primary text-xs font-semibold mb-7 tracking-wide">
              BUILT BY STUDENTS, FOR STUDENTS <TrendingUp className="w-3.5 h-3.5" />
            </div>

            <h1
              className="text-5xl md:text-6xl lg:text-7xl font-bold leading-[1.05] mb-6"
              style={{ fontFamily: DISPLAY_FONT }}
            >
              Find Your Next
              <span className="block text-primary italic">Favourite Stall</span>
            </h1>

            <p className="text-lg text-muted-foreground mb-8 leading-relaxed">
              Discover hidden gems across 13 canteens, a variety of cafes, fast food outlets and restaurants — rated, reviewed, and recommended by your fellow NTU foodies.
            </p>

            {/* Search bar */}
            <div className="flex gap-3 mb-7">
              <div className="flex-1 flex items-center gap-3 px-4 py-3 rounded-xl bg-card border border-border focus-within:border-primary/40 transition-colors">
                <Search className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search stalls, dishes, canteens..."
                  className="bg-transparent text-sm text-foreground placeholder:text-muted-foreground outline-none flex-1"
                />
              </div>
              <button className="px-5 py-3 rounded-xl bg-primary text-primary-foreground font-semibold text-sm hover:opacity-90 transition-opacity">
                Search
              </button>
            </div>

            {/* Quick tags */}
            <div className="flex flex-wrap gap-2 mb-10">
              {[
                "🍗 Chicken Rice",
                "🍜 Ban Mian",
                "🌶️ Mala",
                "🍱 Bento",
                "🥘 Economy Rice",
                "🍣 Japanese",
              ].map((tag) => (
                <button
                  key={tag}
                  className="px-3 py-1.5 rounded-full text-xs border border-border text-muted-foreground hover:border-primary/40 hover:text-foreground transition-all duration-200"
                >
                  {tag}
                </button>
              ))}
            </div>

            {/* Stats */}
            <div className="flex gap-10">
              {[
                ["50+", "Food Stalls"],
                ["2,400+", "Reviews"],
                ["13", "Canteens"],
              ].map(([num, label]) => (
                <div key={label}>
                  <div
                    className="text-3xl font-bold text-foreground"
                    style={{ fontFamily: DISPLAY_FONT }}
                  >
                    {num}
                  </div>
                  <div className="text-xs text-muted-foreground mt-0.5">
                    {label}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ── CAMPUS MAP TEASER ────────────────────────── */}
<section className="py-24 bg-card border-t border-border">
  <div className="max-w-7xl mx-auto px-6">
    <div className="text-center mb-12">
      <p className="text-[#1B2D4F] text-xs font-bold uppercase tracking-widest mb-2">
        Navigate Campus
      </p>
      <h2
        className="text-3xl md:text-4xl font-bold mb-4"
        style={{ fontFamily: DISPLAY_FONT }}
      >
        All Food Places in 1 Map
      </h2>
      <p className="text-muted-foreground max-w-sm mx-auto text-sm leading-relaxed">
        Check what's available and plan your route in seconds.
      </p>
    </div>

    <VendorMap compact />

    <div className="text-center mt-8">
      <Link
        to="/map"
        className="inline-flex items-center gap-1.5 text-sm font-semibold text-primary hover:underline"
      >
        View full map <ChevronRight className="w-4 h-4" />
      </Link>
    </div>
  </div>
</section>

      {/* ── REVIEWS SECTION ───────────────────────────── */}
      <section className="py-24 bg-card border-t border-border">
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center mb-16">
            <p className="text-primary text-xs font-bold uppercase tracking-widest mb-2">
              Real Voices
            </p>
            <h2
              className="text-3xl md:text-4xl font-bold"
              style={{ fontFamily: DISPLAY_FONT }}
            >
              Latest Student Reviews
            </h2>
          </div>

          <div className="grid md:grid-cols-3 gap-6">
            {REVIEWS.map((review) => (
              <div
                key={review.id}
                className="p-6 rounded-2xl bg-background border border-border flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-center gap-3 mb-4">
                    <div className="w-10 h-10 rounded-full bg-primary/10 text-primary font-bold flex items-center justify-center text-sm">
                      {review.initials}
                    </div>
                    <div>
                      <h4 className="text-sm font-bold text-foreground">
                        {review.user}
                      </h4>
                      <p className="text-xs text-muted-foreground">
                        {review.programme}
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center justify-between mb-3">
                    <StarRow rating={review.rating} />
                    <span className="text-xs text-muted-foreground">
                      {review.date}
                    </span>
                  </div>

                  <p className="text-sm text-foreground/90 leading-relaxed mb-4">
                    {review.text}
                  </p>
                </div>

                <div className="flex items-center justify-between text-xs text-muted-foreground pt-4 border-t border-border">
                  <span className="font-semibold text-foreground">
                    {review.stall}
                  </span>
                  <button className="flex items-center gap-1 hover:text-foreground transition-colors">
                    <ThumbsUp className="w-3.5 h-3.5" />
                    <span>{review.helpful}</span>
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── FLOATING CHATBOT WIDGET ───────────────────── */}
      <div className="fixed bottom-6 right-6 z-50">
        {chatOpen ? (
          <div className="w-80 sm:w-96 rounded-2xl bg-card border border-border shadow-2xl flex flex-col overflow-hidden transition-all">
            {/* Header */}
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

            {/* Messages */}
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
                  {msg.text}
                </div>
              ))}
              {isTyping && (
                <div className="self-start text-xs text-muted-foreground italic flex items-center gap-1">
                  <Clock className="w-3 h-3 animate-spin" /> Thinking...
                </div>
              )}
            </div>

            {/* Quick Prompts */}
            <div className="px-3 py-2 bg-card border-t border-border flex flex-wrap gap-1">
              {SUGGESTED_QUESTIONS.map((q) => (
                <button
                  key={q}
                  onClick={() => sendMessage(q)}
                  className="text-[10px] px-2 py-1 rounded-md bg-muted text-muted-foreground hover:text-foreground transition-colors"
                >
                  {q}
                </button>
              ))}
            </div>

            {/* Input */}
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

function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/food" element={<FoodPage />} />
      <Route path="/food/vendors/:vendorId" element={<VendorsPage />} />
      <Route path="/map" element={<VendorMap />} />
    </Routes>
  );
}

export default App;