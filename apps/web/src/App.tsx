import { useRef, useState } from "react";
import { Routes, Route, Link } from "react-router-dom";
import { askChat, chatErrorMessage } from "./api/chat";
import FoodPage from "./pages/FoodPage";
import VendorsPage from "./pages/VendorsPage";
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
{["Discover", "Reviews", "Map"].map((link) =>
  link === "Discover" ? (
    <Link
      key={link}
      to="/food"
      className="text-muted-foreground hover:text-foreground transition-colors"
    >
      {link}
    </Link>
  ) : (
    <a
      key={link}
      href="#"
      className="text-muted-foreground hover:text-foreground transition-colors"
    >
      {link}
    </a>
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
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-primary/30 bg-primary/10 text-primary text-xs font-semibold mb-7 tracking-wide"> BUILT BY STUDENTS, FOR STUDENTS<TrendingUp className="w-3.5 h-3.5" /></div>

            <h1
              className="text-5xl md:text-6xl lg:text-7xl font-bold leading-[1.05] mb-6"
              style={{ fontFamily: DISPLAY_FONT }}
            >
              Find Your Next
              <span className="block text-primary italic">Favourite Stall</span>
            </h1>

            <p className="text-lg text-muted-foreground mb-8 leading-relaxed"> Discover hidden gems across 13 canteens, a variety of cafes, fast food outlets and restaurants — rated, reviewed, and recommended by your fellow NTU foodies.</p>

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
            >All Food Places in 1 Map</h2>
            <p className="text-muted-foreground max-w-sm mx-auto text-sm leading-relaxed">Check what's available and plan your route in seconds.</p>
          </div>

          <div
            className="relative w-full rounded-3xl overflow-hidden mb-10"
            style={{ height: '520px', boxShadow: '0 8px 40px rgba(0,0,0,0.12), 0 2px 8px rgba(0,0,0,0.06)' }}
          >
            {/* Floating legend */}
            <div
              className="absolute top-4 left-4 z-10 rounded-2xl px-4 py-3.5"
              style={{
                background: 'rgba(255,255,255,0.97)',
                backdropFilter: 'blur(16px)',
                boxShadow: '0 2px 16px rgba(0,0,0,0.10)',
                border: '1px solid rgba(0,0,0,0.05)',
              }}
            >
              <p style={{ fontSize: 9, fontWeight: 800, letterSpacing: '0.12em', color: '#8A8070', textTransform: 'uppercase', marginBottom: 10, fontFamily: 'system-ui,sans-serif' }}>
                Map Legend
              </p>
              {([
                { color: '#C41230', label: 'Canteen' },
                { color: '#1B2D4F', label: 'Food Court' },
                { color: '#D97706', label: 'Café' },
              ] as const).map((item) => (
                <div key={item.label} style={{ display: 'flex', alignItems: 'center', gap: 9, marginBottom: 7 }}>
                  <svg width="13" height="18" viewBox="0 0 13 18" style={{ flexShrink: 0 }}>
                    <path d="M 6.5,17 C 2.5,11 0,8.5 0,5.5 A 6.5,6.5 0 1,1 13,5.5 C 13,8.5 10.5,11 6.5,17 Z" fill={item.color} />
                    <circle cx="6.5" cy="5.5" r="2.5" fill="white" />
                  </svg>
                  <span style={{ fontSize: 10.5, color: '#3A3530', fontFamily: 'system-ui,sans-serif', fontWeight: 500 }}>{item.label}</span>
                </div>
              ))}
            </div>

            <svg viewBox="0 0 860 520" className="w-full h-full" xmlns="http://www.w3.org/2000/svg">
              <defs>
                <pattern id="fine-dots" x="0" y="0" width="20" height="20" patternUnits="userSpaceOnUse">
                  <circle cx="10" cy="10" r="0.65" fill="#B8B0A0" />
                </pattern>
                <linearGradient id="campus-fill" x1="0" y1="0" x2="0.6" y2="1">
                  <stop offset="0%" stopColor="#DEF0C8" />
                  <stop offset="100%" stopColor="#D0E4B8" />
                </linearGradient>
                <linearGradient id="water-fill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#B8D8F0" />
                  <stop offset="100%" stopColor="#A0C8E4" />
                </linearGradient>
                <filter id="bld-shadow" x="-20%" y="-20%" width="160%" height="160%">
                  <feDropShadow dx="2" dy="3" stdDeviation="3" floodColor="#2A3A20" floodOpacity="0.14" />
                </filter>
                <filter id="tip-float" x="-30%" y="-30%" width="160%" height="180%">
                  <feDropShadow dx="0" dy="4" stdDeviation="6" floodColor="#000" floodOpacity="0.14" />
                </filter>
              </defs>

              {/* ── Off-campus parchment ── */}
              <rect width="860" height="520" fill="#E8E2D8" />
              <rect width="860" height="520" fill="url(#fine-dots)" opacity="0.8" />

              {/* ── Campus ground ── */}
              <path
                d="M 92,168 C 118,104 182,68 182,68 L 414,38 L 624,38 C 706,50 762,96 762,96 L 814,198 L 814,370 C 798,424 742,448 742,448 L 558,486 L 278,486 C 192,486 114,428 114,428 C 76,396 62,310 62,310 Z"
                fill="url(#campus-fill)"
              />
              <path
                d="M 92,168 C 118,104 182,68 182,68 L 414,38 L 624,38 C 706,50 762,96 762,96 L 814,198 L 814,370 C 798,424 742,448 742,448 L 558,486 L 278,486 C 192,486 114,428 114,428 C 76,396 62,310 62,310 Z"
                fill="none" stroke="#B8D098" strokeWidth="2"
              />

              {/* ── Lawn / park areas ── */}
              <ellipse cx="318" cy="170" rx="64" ry="40" fill="#C0D8A0" opacity="0.65" />
              <ellipse cx="538" cy="164" rx="50" ry="32" fill="#C0D8A0" opacity="0.55" />
              <ellipse cx="324" cy="380" rx="60" ry="36" fill="#C0D8A0" opacity="0.60" />
              <ellipse cx="578" cy="388" rx="46" ry="30" fill="#C0D8A0" opacity="0.55" />

              {/* ── Water features ── */}
              <ellipse cx="186" cy="428" rx="42" ry="24" fill="url(#water-fill)" />
              <ellipse cx="186" cy="428" rx="36" ry="18" fill="#B8D8F0" opacity="0.55" />
              <text x="186" y="432" fontSize="7" fill="#4A80A8" textAnchor="middle" fontFamily="system-ui,sans-serif" fontStyle="italic" fontWeight="500">Yunnan Lake</text>
              <ellipse cx="672" cy="452" rx="28" ry="16" fill="url(#water-fill)" />
              <ellipse cx="672" cy="452" rx="22" ry="11" fill="#B8D8F0" opacity="0.5" />

              {/* ── Primary roads ── */}
              <path d="M 62,252 L 814,252" stroke="#D8CEBC" strokeWidth="20" strokeLinecap="butt" />
              <path d="M 62,252 L 814,252" stroke="#F0EAE0" strokeWidth="16" strokeLinecap="butt" />
              <path d="M 440,38 L 440,486" stroke="#D8CEBC" strokeWidth="16" strokeLinecap="butt" />
              <path d="M 440,38 L 440,486" stroke="#F0EAE0" strokeWidth="12" strokeLinecap="butt" />

              {/* ── Secondary roads ── */}
              <path d="M 278,252 Q 194,316 114,372" stroke="#E0D8C8" strokeWidth="10" fill="none" strokeLinecap="round" />
              <path d="M 278,252 Q 194,316 114,372" stroke="#EDE6DC" strokeWidth="7" fill="none" strokeLinecap="round" />
              <path d="M 622,252 Q 696,308 742,388" stroke="#E0D8C8" strokeWidth="10" fill="none" strokeLinecap="round" />
              <path d="M 622,252 Q 696,308 742,388" stroke="#EDE6DC" strokeWidth="7" fill="none" strokeLinecap="round" />
              <path d="M 182,68 Q 202,152 202,252" stroke="#E0D8C8" strokeWidth="9" fill="none" strokeLinecap="round" />
              <path d="M 182,68 Q 202,152 202,252" stroke="#EDE6DC" strokeWidth="6" fill="none" strokeLinecap="round" />
              <path d="M 762,96 Q 794,152 814,198" stroke="#E0D8C8" strokeWidth="9" fill="none" strokeLinecap="round" />
              <path d="M 762,96 Q 794,152 814,198" stroke="#EDE6DC" strokeWidth="6" fill="none" strokeLinecap="round" />

              {/* Road centre dashes */}
              <path d="M 62,252 L 814,252" stroke="#C8C0AE" strokeWidth="1.2" strokeDasharray="18,14" opacity="0.7" />
              <path d="M 440,38 L 440,486" stroke="#C8C0AE" strokeWidth="1.2" strokeDasharray="18,14" opacity="0.7" />

              {/* Road labels */}
              <text x="168" y="245" fontSize="7.5" fill="#9A9080" fontFamily="system-ui,sans-serif" fontWeight="700" letterSpacing="1.5">NANYANG AVE</text>
              <text x="448" y="172" fontSize="7.5" fill="#9A9080" fontFamily="system-ui,sans-serif" fontWeight="700" letterSpacing="1.5" writingMode="tb">NANYANG DRIVE</text>

              {/* ── Buildings ── */}
              {/* North Spine */}
              <rect x="372" y="90" width="138" height="72" rx="6" fill="#9AAE90" filter="url(#bld-shadow)" />
              <rect x="380" y="98" width="122" height="56" rx="5" fill="#8EA284" />
              <rect x="388" y="106" width="106" height="40" rx="4" fill="#849878" opacity="0.8" />
              {/* The Hive */}
              <rect x="356" y="210" width="120" height="96" rx="12" fill="#9AAE90" filter="url(#bld-shadow)" />
              <rect x="364" y="218" width="104" height="80" rx="10" fill="#8EA284" />
              <rect x="372" y="226" width="88" height="64" rx="8" fill="#849878" opacity="0.7" />
              {/* South Spine */}
              <rect x="374" y="338" width="132" height="68" rx="6" fill="#9AAE90" filter="url(#bld-shadow)" />
              <rect x="382" y="346" width="116" height="52" rx="5" fill="#8EA284" />
              {/* Pioneer */}
              <rect x="84" y="248" width="104" height="80" rx="6" fill="#9AAE90" filter="url(#bld-shadow)" />
              <rect x="92" y="256" width="88" height="64" rx="5" fill="#8EA284" />
              {/* Foodgle Hub */}
              <rect x="620" y="228" width="112" height="80" rx="6" fill="#9AAE90" filter="url(#bld-shadow)" />
              <rect x="628" y="236" width="96" height="64" rx="5" fill="#8EA284" />
              {/* WKWSCI */}
              <rect x="614" y="96" width="100" height="70" rx="6" fill="#9AAE90" filter="url(#bld-shadow)" />
              <rect x="622" y="104" width="84" height="54" rx="5" fill="#8EA284" />
              {/* North Hill */}
              <rect x="168" y="82" width="94" height="66" rx="6" fill="#9AAE90" filter="url(#bld-shadow)" />
              <rect x="176" y="90" width="78" height="50" rx="5" fill="#8EA284" />
              {/* Canteen 2 */}
              <rect x="256" y="174" width="98" height="62" rx="6" fill="#9AAE90" filter="url(#bld-shadow)" />
              <rect x="264" y="182" width="82" height="46" rx="5" fill="#8EA284" />
              {/* Halls (cooler, muted) */}
              <rect x="114" y="360" width="64" height="56" rx="5" fill="#A8B4C0" opacity="0.60" />
              <rect x="186" y="386" width="58" height="48" rx="5" fill="#A8B4C0" opacity="0.60" />
              <rect x="630" y="364" width="62" height="56" rx="5" fill="#A8B4C0" opacity="0.60" />
              <rect x="696" y="386" width="56" height="50" rx="5" fill="#A8B4C0" opacity="0.60" />
              <rect x="282" y="416" width="56" height="44" rx="5" fill="#A8B4C0" opacity="0.55" />
              <rect x="504" y="418" width="56" height="44" rx="5" fill="#A8B4C0" opacity="0.55" />

              {/* Building micro-labels */}
              <text x="441" y="136" fontSize="7" fill="#3A4E34" textAnchor="middle" fontFamily="system-ui,sans-serif" fontWeight="800" letterSpacing="0.8" opacity="0.8">NORTH SPINE</text>
              <text x="416" y="262" fontSize="7" fill="#3A4E34" textAnchor="middle" fontFamily="system-ui,sans-serif" fontWeight="800" letterSpacing="0.8" opacity="0.8">THE HIVE</text>
              <text x="440" y="378" fontSize="7" fill="#3A4E34" textAnchor="middle" fontFamily="system-ui,sans-serif" fontWeight="800" letterSpacing="0.8" opacity="0.8">SOUTH SPINE</text>

              {/* ── Trees ── */}
              {([
                [314,152,15],[494,152,13],[296,394,14],[600,152,12],[214,316,13],
                [662,314,13],[502,90,12],[356,426,13],[250,198,12],[732,184,13],
                [404,462,12],[144,194,11],[526,460,12],[664,464,11],[584,462,11],
                [100,358,11],[744,358,12],[492,338,11],[332,336,11],[202,158,12],
                [680,152,11],[136,302,10],[750,288,10],[348,466,10],
              ] as const).map(([cx, cy, r], i) => (
                <g key={i}>
                  <circle cx={cx} cy={cy + 2} r={r + 1} fill="#5A8040" opacity="0.18" />
                  <circle cx={cx} cy={cy} r={r + 1} fill="#88C060" opacity="0.55" />
                  <circle cx={cx} cy={cy} r={r - 1} fill="#78B050" opacity="0.80" />
                  <circle cx={cx} cy={cy} r={r - 5} fill="#68A040" opacity="0.90" />
                </g>
              ))}

              {/* ── Campus gate ── */}
              <g transform="translate(820,236)">
                <rect x="0" y="0" width="7" height="32" rx="2" fill="#88806E" />
                <rect x="14" y="0" width="7" height="32" rx="2" fill="#88806E" />
                <rect x="-2" y="-7" width="25" height="7" rx="2" fill="#78705E" />
                <line x1="3.5" y1="0" x2="3.5" y2="32" stroke="#9E9484" strokeWidth="0.5" strokeDasharray="3,3" />
                <line x1="17.5" y1="0" x2="17.5" y2="32" stroke="#9E9484" strokeWidth="0.5" strokeDasharray="3,3" />
              </g>
              <text x="829" y="224" fontSize="7" fill="#78706A" fontFamily="system-ui,sans-serif" textAnchor="middle" fontWeight="700" letterSpacing="0.5">MAIN GATE</text>

              {/* ── Food pins (teardrop) ── */}
              {([
                { x: 440, y: 98,  n1: "North Spine Food Court", sub: "Canteen · 18 stalls",    color: "#C41230", tipRight: true  },
                { x: 215, y: 94,  n1: "North Hill Food Court",  sub: "Canteen · 12 stalls",    color: "#C41230", tipRight: true  },
                { x: 416, y: 248, n1: "Koufu @ The Hive",       sub: "Food Court · 10 stalls", color: "#1B2D4F", tipRight: false },
                { x: 440, y: 356, n1: "South Spine Food Court", sub: "Canteen · 14 stalls",    color: "#C41230", tipRight: false },
                { x: 136, y: 272, n1: "Pioneer Canteen",        sub: "Canteen · 22 stalls",    color: "#C41230", tipRight: true  },
                { x: 676, y: 262, n1: "Foodgle Hub",            sub: "Food Court · 16 stalls", color: "#1B2D4F", tipRight: false },
                { x: 548, y: 208, n1: "The Quad Café",          sub: "Café · 4 outlets",       color: "#D97706", tipRight: true  },
                { x: 664, y: 116, n1: "WKWSCI Canteen",        sub: "Canteen · 8 stalls",     color: "#C41230", tipRight: false },
                { x: 306, y: 196, n1: "Canteen 2",              sub: "Canteen · 10 stalls",    color: "#C41230", tipRight: true  },
                { x: 566, y: 392, n1: "Campus Creamery",        sub: "Café · 3 outlets",       color: "#D97706", tipRight: false },
              ] as const).map((pin, i) => {
                const tipX = pin.tipRight ? pin.x + 24 : pin.x - 176;
                const tipY = pin.y < 118 ? pin.y + 10 : pin.y - 80;
                return (
                  <g key={i} className="group cursor-pointer">
                    {/* Pin shadow */}
                    <g transform={`translate(${pin.x}, ${pin.y - 4})`}>
                      <path
                        d="M 0,8 C -6,-2 -17,-12 -17,-22 A 17,17 0 1,1 17,-22 C 17,-12 6,-2 0,8 Z"
                        fill="rgba(0,0,0,0.20)"
                        transform="translate(0,5) scale(1,0.4)"
                      />
                    </g>
                    {/* Teardrop pin */}
                    <g transform={`translate(${pin.x}, ${pin.y - 4})`}>
                      <path
                        d="M 0,8 C -6,-2 -17,-12 -17,-22 A 17,17 0 1,1 17,-22 C 17,-12 6,-2 0,8 Z"
                        fill={pin.color}
                        stroke="white"
                        strokeWidth="2.5"
                        strokeLinejoin="round"
                      />
                      <circle cx="0" cy="-22" r="7" fill="white" />
                      <circle cx="0" cy="-22" r="3.5" fill={pin.color} />
                    </g>
                    {/* Tooltip */}
                    <g
                      transform={`translate(${tipX},${tipY})`}
                      className="opacity-0 group-hover:opacity-100 transition-all duration-200 pointer-events-none"
                      filter="url(#tip-float)"
                    >
                      {/* Shadow offset */}
                      <rect x="2" y="2" width="164" height="58" rx="12" fill="rgba(0,0,0,0.08)" />
                      {/* Card */}
                      <rect x="0" y="0" width="164" height="58" rx="12" fill="white" />
                      {/* Colored header */}
                      <rect x="0" y="0" width="164" height="26" rx="12" fill={pin.color} />
                      <rect x="0" y="16" width="164" height="10" fill={pin.color} />
                      <text x="12" y="17" fontSize="10" fontWeight="700" fill="white" fontFamily="system-ui,sans-serif">{pin.n1}</text>
                      {/* Body */}
                      <text x="12" y="44" fontSize="9" fill="#5A5550" fontFamily="system-ui,sans-serif">{pin.sub}</text>
                    </g>
                  </g>
                );
              })}

              {/* ── Compass ── */}
              <g transform="translate(50,66)">
                <circle cx="0" cy="0" r="28" fill="white" fillOpacity="0.95" />
                <circle cx="0" cy="0" r="28" stroke="#D8D0C4" strokeWidth="1" fill="none" />
                <circle cx="0" cy="0" r="4" fill="#C41230" />
                {/* N needle */}
                <path d="M 0,0 L -5,-22 L 0,-26 L 5,-22 Z" fill="#C41230" />
                {/* S needle */}
                <path d="M 0,0 L -4,20 L 0,24 L 4,20 Z" fill="#B0A898" />
                {/* E/W ticks */}
                <path d="M 22,0 L 28,0" stroke="#B0A898" strokeWidth="1.5" strokeLinecap="round" />
                <path d="M -28,0 L -22,0" stroke="#B0A898" strokeWidth="1.5" strokeLinecap="round" />
                <text x="0" y="-30" fontSize="8" fontWeight="800" fill="#C41230" fontFamily="system-ui,sans-serif" textAnchor="middle">N</text>
                <text x="0" y="40" fontSize="7.5" fill="#9A9080" fontFamily="system-ui,sans-serif" textAnchor="middle">S</text>
                <text x="34" y="3" fontSize="7.5" fill="#9A9080" fontFamily="system-ui,sans-serif">E</text>
                <text x="-38" y="3" fontSize="7.5" fill="#9A9080" fontFamily="system-ui,sans-serif">W</text>
              </g>

              {/* ── Scale bar ── */}
              <g transform="translate(686,492)">
                <rect x="0" y="0" width="40" height="4" rx="1" fill="#8A8070" />
                <rect x="40" y="0" width="40" height="4" rx="1" fill="#C8C0B0" />
                <rect x="0" y="-1" width="80" height="6" rx="1" fill="none" stroke="#8A8070" strokeWidth="1" />
                <text x="0" y="-5" fontSize="7.5" fill="#8A8070" fontFamily="system-ui,sans-serif" textAnchor="middle">0</text>
                <text x="40" y="-5" fontSize="7.5" fill="#8A8070" fontFamily="system-ui,sans-serif" textAnchor="middle">250m</text>
                <text x="80" y="-5" fontSize="7.5" fill="#8A8070" fontFamily="system-ui,sans-serif" textAnchor="middle">500m</text>
              </g>

              {/* ── Campus label ── */}
              <text x="430" y="514" fontSize="9.5" fill="#9A9080" textAnchor="middle" fontFamily="system-ui,sans-serif" fontStyle="italic" letterSpacing="0.5">
                Nanyang Technological University · Singapore
              </text>
            </svg>
          </div>

          <div className="text-center">
            
          </div>
        </div>
      </section>

      {/* ── FEATURES ─────────────────────────────────── */}
      

      {/* ── TRENDING STALLS ───────────────────────────── */}
      <section className="py-24">
        <div className="max-w-7xl mx-auto px-6">
          <div className="flex items-end justify-between mb-12">
            <div>
              <p className="text-primary text-xs font-bold uppercase tracking-widest mb-2">
                This Week's Picks
              </p>
              <h2
                className="text-3xl md:text-4xl font-bold"
                style={{ fontFamily: DISPLAY_FONT }}
              >
                Trending on Campus
              </h2>
            </div>
<Link
  to="/food"
  className="hidden md:flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
>
  View all stalls{" "}
  <ChevronRight className="w-4 h-4" />
</Link>
          </div>

          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
            {STALLS.map((stall) => (
              <div
                key={stall.id}
                className="group rounded-2xl border border-border bg-card overflow-hidden hover:border-primary/25 transition-all duration-300 cursor-pointer"
              >
                <div className="relative h-44 overflow-hidden bg-muted">
                  <img
                    src={stall.image}
                    alt={`${stall.name} dish`}
                    className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                  />
                  <div className="absolute top-3 left-3 flex gap-1.5 flex-wrap">
                    {stall.tags.map((tag) => (
                      <span
                        key={tag}
                        className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-background/75 text-foreground border border-border/60 backdrop-blur-sm"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                  <div className="absolute top-3 right-3 px-2 py-1 rounded-lg bg-primary text-primary-foreground text-xs font-bold">
                    {stall.rating}★
                  </div>
                </div>

                <div className="p-4">
                  <h3 className="font-semibold text-sm leading-snug mb-1">
                    {stall.name}
                  </h3>
                  <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-3">
                    <MapPin className="w-3 h-3 flex-shrink-0" />
                    {stall.canteen}
                  </div>
                  <div className="flex items-center justify-between text-xs text-muted-foreground mb-3">
                    <StarRow rating={stall.rating} />
                    <span>{stall.reviews} reviews</span>
                  </div>
                  <p className="text-xs text-muted-foreground leading-relaxed line-clamp-2 border-t border-border pt-3">
                    &ldquo;{stall.topReview}&rdquo;
                  </p>
                  <div className="flex items-center justify-between mt-3">
                    <span className="text-xs font-bold text-foreground">
                      {stall.price}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {stall.cuisine}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── REVIEWS ──────────────────────────────────── */}
      <section className="py-24 bg-card border-y border-border">
        <div className="max-w-7xl mx-auto px-6">
          <div className="flex items-end justify-between mb-12">
            <div>
              <p className="text-[#1B2D4F] text-xs font-bold uppercase tracking-widest mb-2">
                From the Community
              </p>
              <h2
                className="text-3xl md:text-4xl font-bold"
                style={{ fontFamily: DISPLAY_FONT }}
              >
                What students are saying
              </h2>
            </div>
            <button className="hidden md:flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors">
              All reviews <ChevronRight className="w-4 h-4" />
            </button>
          </div>

          <div className="grid md:grid-cols-3 gap-6">
            {REVIEWS.map((review) => (
              <div
                key={review.id}
                className="p-6 rounded-2xl border border-border bg-background flex flex-col"
              >
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-full bg-primary/20 flex items-center justify-center text-primary text-sm font-bold flex-shrink-0">
                      {review.initials}
                    </div>
                    <div>
                      <div className="text-sm font-semibold">{review.user}</div>
                      <div className="text-xs text-muted-foreground">
                        {review.programme}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-1 text-xs text-muted-foreground">
                    <Clock className="w-3 h-3" />
                    {review.date}
                  </div>
                </div>

                <div className="flex items-center gap-2 mb-3">
                  <StarRow rating={review.rating} />
                  <span className="text-xs text-muted-foreground">at</span>
                  <span className="text-xs font-semibold text-primary truncate">
                    {review.stall}
                  </span>
                </div>

                <p className="text-sm text-muted-foreground leading-relaxed flex-1 mb-4">
                  &ldquo;{review.text}&rdquo;
                </p>

                <div className="flex items-center justify-between text-xs text-muted-foreground border-t border-border pt-3">
                  <div className="flex items-center gap-1.5">
                    <MapPin className="w-3 h-3" />
                    {review.canteen}
                  </div>
                  <button className="flex items-center gap-1.5 hover:text-foreground transition-colors">
                    <ThumbsUp className="w-3 h-3" />
                    {review.helpful} helpful
                  </button>
                </div>
              </div>
            ))}
          </div>

          <div className="text-center mt-10">
            <button className="inline-flex items-center gap-2 px-6 py-3 rounded-xl border border-border text-sm font-semibold text-foreground hover:border-primary/40 transition-colors">
              Load more reviews <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </section>

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
                onClick={() => setChatOpen(false)}
                className="text-muted-foreground hover:text-foreground transition-colors p-1"
                aria-label="Close chat"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Messages */}
            <div
              className="p-4 h-72 overflow-y-auto flex flex-col gap-3 bg-background"
              style={{ scrollbarWidth: "none" }}
            >
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
                          style={{ animationDelay: `${i * 0.15}s` }}
                        />
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Suggested + input */}
            <div className="px-4 pt-2 pb-4 border-t border-border bg-card">
              <div className="flex flex-wrap gap-1.5 mb-3">
                {SUGGESTED_QUESTIONS.map((q) => (
                  <button
                    key={q}
                    onClick={() => sendMessage(q)}
                    disabled={isTyping}
                    className="text-xs px-2.5 py-1.5 rounded-full border border-border text-muted-foreground hover:border-primary/40 hover:text-foreground transition-all duration-200 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {q}
                  </button>
                ))}
              </div>
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
                  onClick={() => sendMessage(chatInput)}
                  disabled={isTyping || !chatInput.trim()}
                  aria-label="Send message"
                  className="w-10 h-10 rounded-xl bg-primary flex items-center justify-center hover:opacity-90 transition-opacity flex-shrink-0 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <Send className="w-4 h-4 text-primary-foreground" />
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Toggle button */}
        <button
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

      {/* ── CTA BANNER ───────────────────────────────── */}
      

      {/* ── FOOTER ───────────────────────────────────── */}
      <footer className="border-t border-border py-10">
        <div className="max-w-7xl mx-auto px-6 flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded bg-primary flex items-center justify-center">
              <Utensils className="w-3 h-3 text-primary-foreground" />
            </div>
            <span
              className="text-sm font-bold"
              style={{ fontFamily: DISPLAY_FONT }}
            >
              NTU Foodie Guide
            </span>
          </div>
          <p className="text-xs text-muted-foreground">Made by NTU students, for NTU students.</p>
          <div className="flex gap-6 text-xs text-muted-foreground">
            {["About", "Contribute", "Privacy"].map((l) => (
              <a
                key={l}
                href="#"
                className="hover:text-foreground transition-colors"
              >
                {l}
              </a>
            ))}
          </div>
        </div>
      </footer>
    </div>
  );
}

function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/food" element={<FoodPage />} />
      <Route path="/food/vendors/:vendorId" element={<VendorsPage />} />
    </Routes>
  );
}

export default App;
