import { useState, useRef, useEffect } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { ChevronDown, LogOut, Menu, Utensils, X, Search, Store, UserRound } from "lucide-react";
import { useAuth } from "../contexts/AuthContext";
import { fetchVendorPage, fetchVendors } from "../api/vendors";
import { rankTrendingVendors } from "../lib/trendingVendors";

const QUICK_SEARCH_TAGS = [
  { emoji: "🍗", label: "Chicken Rice", query: "Chicken Rice" },
  { emoji: "🍜", label: "Ban Mian", query: "Ban Mian" },
  { emoji: "🌶️", label: "Mala", query: "Mala" },
  { emoji: "🍱", label: "Bento", query: "Bento" },
  { emoji: "🥘", label: "Economy Rice", query: "Economy Rice" },
  { emoji: "🍣", label: "Japanese", query: "Japanese" },
];

export default function Header({ fixed = false }: { fixed?: boolean }) {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [accountMenuOpen, setAccountMenuOpen] = useState(false);
  const [mobileSearchOpen, setMobileSearchOpen] = useState(false);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [recommendedStalls, setRecommendedStalls] = useState<any[]>([]);

  const navigate = useNavigate();
  const location = useLocation();
  const { loading, user, signOut } = useAuth();

  const metadataDisplayName = typeof user?.user_metadata?.display_name === "string"
    && user.user_metadata.display_name.trim()
    ? user.user_metadata.display_name.trim()
    : null;
  const displayName = metadataDisplayName ?? user?.email ?? "Account";

  const handleSignOut = async () => {
    await signOut();
    setAccountMenuOpen(false);
    setMobileMenuOpen(false);
  };

  const authControls = !loading && (
    user ? (
      <div className="relative">
        <button
          type="button"
          onClick={() => setAccountMenuOpen((open) => !open)}
          className="flex w-full items-center justify-between gap-1.5 px-0.25 rounded-s text-sm font-semibold text-foreground cursor-pointer hover:bg-muted transition-colors"
          aria-expanded={accountMenuOpen}
          aria-haspopup="menu"
          aria-label="Open account menu"
        >
          <span className="truncate">{displayName}</span>
          <ChevronDown className="h-4 w-4 mt-0.75 shrink-0 text-muted-foreground" />
        </button>

        {accountMenuOpen && (
          <div
            className="static mt-2 w-full min-w-44 rounded-md border border-border bg-card shadow-lg md:absolute md:right-0 md:top-full md:w-auto"
            role="menu"
          >
            <div className="border-b border-border px-3 py-2 text-xs text-muted-foreground">
              {user.email}
            </div>
            <Link
              to="/account"
              onClick={() => {
                setAccountMenuOpen(false);
                setMobileMenuOpen(false);
              }}
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-muted-foreground cursor-pointer hover:bg-muted hover:text-foreground transition-colors"
              role="menuitem"
            >
              <UserRound className="h-4 w-4" />
              Account
            </Link>
            <button
              type="button"
              onClick={handleSignOut}
              className="flex w-full items-center rounded-b-sm gap-2 px-3 py-2 text-left text-sm text-muted-foreground cursor-pointer hover:bg-muted hover:text-foreground transition-colors"
              role="menuitem"
            >
              <LogOut className="h-4 w-4" />
              Sign Out
            </button>
          </div>
        )}
      </div>
    ) : (
      <Link
        to="/signin"
        state={{ from: location.pathname }}
        className="text-sm text-muted-foreground hover:text-foreground transition-colors"
      >
        Sign In
      </Link>
    )
  );

  const searchContainerRef = useRef<HTMLDivElement>(null);
  const mobileSearchRef = useRef<HTMLDivElement>(null);

  // Close dropdown or mobile search when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        searchContainerRef.current &&
        !searchContainerRef.current.contains(event.target as Node)
      ) {
        setDropdownOpen(false);
      }
      if (
        mobileSearchRef.current &&
        !mobileSearchRef.current.contains(event.target as Node)
      ) {
        setMobileSearchOpen(false);
      }
    }

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);


  useEffect(() => {
    if (loading) return;

    const controller = new AbortController();

    async function loadRecommendedStalls() {
  // Logged-in users: try personalized recommendations first.
    if (user) {
      try {
        const data = await fetchVendorPage({
          sort: "recommended",
          limit: 4,
          signal: controller.signal,
        });

        const personalized = (data.items ?? []).filter(
          (vendor: any) => vendor.recommended,
        );

        if (personalized.length > 0) {
          setRecommendedStalls(personalized.slice(0, 4));
          return;
        }
      } catch (error) {
        if (controller.signal.aborted) return;

        console.warn(
          "Personalized recommendations unavailable, using trending stalls.",
          error,
        );
      }
    }

  // Logged-out users, users without recommendations,
  // or recommendation failures fall back to trending.
    try {
      const vendors = await fetchVendors("", controller.signal);
      setRecommendedStalls(rankTrendingVendors(vendors, 4));
    } catch (error) {
      if (!controller.signal.aborted) {
        console.error("Failed to load trending stalls:", error);
        setRecommendedStalls([]);
      }
    }
  }

    void loadRecommendedStalls();

    return () => controller.abort();
  }, [user, loading]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const query = searchQuery.trim();
    setDropdownOpen(false);
    setMobileSearchOpen(false);

    if (query) {
      navigate(`/food?q=${encodeURIComponent(query)}`);
    } else {
      navigate("/food");
    }
  };

  const handleSelectSearch = (query: string) => {
    setSearchQuery(query);
    setDropdownOpen(false);
    setMobileSearchOpen(false);
    navigate(`/food?q=${encodeURIComponent(query)}`);
  };

  const toggleMobileMenu = () => {
    if (!mobileMenuOpen) {
      setMobileSearchOpen(false);
    }
    setMobileMenuOpen(!mobileMenuOpen);
  };

  const toggleMobileSearch = () => {
    if (!mobileSearchOpen) {
      setMobileMenuOpen(false);
    }
    setMobileSearchOpen(!mobileSearchOpen);
  };

  return (
    <nav
      className={`${
        fixed ? "fixed top-0 left-0 right-0" : "sticky top-0"
      } z-40 w-full border-b border-border bg-background/80 sm:backdrop-blur-md`}
    >
      <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between gap-4">
        {/* Logo / Brand Name */}
        <Link to="/" className="flex items-center gap-2.5 flex-shrink-0">
          <div className="w-8 h-8 rounded-sm bg-primary flex items-center justify-center">
            <Utensils className="w-4 h-4 text-primary-foreground" />
          </div>
          <span className="text-lg font-bold text-foreground font-display">
            NTUmmy
          </span>
        </Link>

        {/* Desktop Centered Search Bar with Dropdown */}
        <div
          ref={searchContainerRef}
          className="hidden md:block flex-1 max-w-md mx-auto relative"
        >
          <form onSubmit={handleSearchSubmit} className="relative">
            <div className="flex items-center gap-2 px-3.5 py-1.5 rounded-full border border-border bg-muted/50 focus-within:bg-background focus-within:border-primary/50 focus-within:ring-1 focus-within:ring-primary/50 transition-all">
              <Search className="w-4 h-4 text-muted-foreground flex-shrink-0" />
              <input
                type="text"
                value={searchQuery}
                onFocus={() => setDropdownOpen(true)}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search dishes, stalls, canteens..."
                className="w-full bg-transparent text-xs text-foreground placeholder:text-muted-foreground outline-none py-1"
              />
              <button
                type="submit"
                className="px-3 py-1 rounded-full bg-primary text-primary-foreground font-semibold text-[11px] hover:opacity-90 active:scale-95 transition-all cursor-pointer flex-shrink-0"
              >
                Search
              </button>
            </div>
          </form>

          {/* Desktop Search Dropdown */}
          {dropdownOpen && (
            <div className="absolute top-full left-0 right-0 mt-2 p-3 bg-card border border-border rounded-2xl shadow-xl z-50 animate-in fade-in slide-in-from-top-1 duration-150">
              {/* Quick Search Section */}
              <p className="text-[11px] font-semibold text-muted-foreground mb-2 px-1">
                Quick Search
              </p>
              <div className="flex flex-wrap gap-1.5 mb-3">
                {QUICK_SEARCH_TAGS.map((tag) => (
                  <button
                    key={tag.label}
                    type="button"
                    onClick={() => handleSelectSearch(tag.query)}
                    className="px-2.5 py-1 rounded-full text-xs border border-border bg-background text-foreground hover:border-primary/40 hover:bg-primary/5 transition-all duration-150 cursor-pointer flex items-center gap-1"
                  >
                    <span>{tag.emoji}</span>
                    <span>{tag.label}</span>
                  </button>
                ))}
              </div>

              {/* Recommended Stalls Section */}
              <div className="border-t border-border pt-2.5">
                <p className="text-[11px] font-semibold text-muted-foreground mb-2 px-1">
                  Recommended Stalls
                </p>
                <div className="flex flex-col gap-1">
                  {recommendedStalls.map((stall) => (
                    <button
                      key={stall.name}
                      type="button"
                      onClick={() => handleSelectSearch(stall.name)}
                      className="w-full text-left px-2 py-1.5 rounded-lg hover:bg-muted/60 transition-colors cursor-pointer flex items-center justify-between gap-2"
                    >
                      <div className="flex items-center gap-2 truncate">
                        <Store className="w-3.5 h-3.5 text-primary flex-shrink-0" />
                        <span className="text-xs font-medium text-foreground truncate">
                          {stall.name}
                        </span>
                      </div>
                      <span className="px-2 py-0.5 rounded-md bg-muted text-[10px] text-muted-foreground font-medium flex-shrink-0">
                        {stall.location}
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Desktop Header Links */}
        <div className="hidden md:flex items-center gap-3 flex-shrink-0">
          {authControls}
          <Link
            to="/food"
            className="text-sm px-4 py-2 rounded-lg bg-primary text-primary-foreground font-semibold hover:opacity-90 transition-opacity"
          >
            Discover
          </Link>
        </div>

        {/* Mobile Action Controls */}
        <div className="flex md:hidden items-center gap-2">
          {/* Mobile Search Toggle Icon */}
          <button
            type="button"
            onClick={toggleMobileSearch}
            className="text-muted-foreground p-1.5 hover:text-foreground transition-colors rounded-lg"
            aria-label="Toggle search"
          >
            <Search className="w-5 h-5" />
          </button>

          {/* Mobile Hamburger Toggle */}
          <button
            type="button"
            className="text-muted-foreground p-1.5 hover:text-foreground transition-colors rounded-lg"
            onClick={toggleMobileMenu}
            aria-label="Toggle menu"
          >
            {mobileMenuOpen ? (
              <X className="w-5 h-5" />
            ) : (
              <Menu className="w-5 h-5" />
            )}
          </button>
        </div>
      </div>

      {/* Expanded Mobile Search Tray */}
      {mobileSearchOpen && (
        <div
          ref={mobileSearchRef}
          className="md:hidden border-t border-border bg-background px-4 py-3 shadow-md animate-in fade-in slide-in-from-top-1 duration-150"
        >
          <form onSubmit={handleSearchSubmit} className="flex gap-2">
            <div className="flex-1 flex items-center gap-2 px-3 py-2 rounded-xl bg-muted/60 border border-border focus-within:border-primary/40">
              <Search className="w-4 h-4 text-muted-foreground flex-shrink-0" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search dishes or stalls..."
                className="w-full bg-transparent text-sm text-foreground placeholder:text-muted-foreground outline-none"
                autoFocus
              />
            </div>
            <button
              type="submit"
              className="px-4 py-2 rounded-xl bg-primary text-primary-foreground font-semibold text-xs hover:opacity-90 transition-opacity"
            >
              Search
            </button>
          </form>

          {/* Quick Tags inside Mobile Search Tray */}
          <div className="flex flex-wrap gap-1.5 mt-3 pt-2 border-t border-border/50">
            {QUICK_SEARCH_TAGS.map((tag) => (
              <button
                key={tag.label}
                type="button"
                onClick={() => handleSelectSearch(tag.query)}
                className="px-2 py-1 rounded-full text-[11px] border border-border bg-card text-foreground"
              >
                {tag.emoji} {tag.label}
              </button>
            ))}
          </div>

          {/* Recommended Stalls inside Mobile Search Tray */}
          <div className="mt-3 pt-2 border-t border-border/50">
            <p className="text-[11px] font-semibold text-muted-foreground mb-1.5">
              Recommended Stalls
            </p>
            <div className="flex flex-col gap-1">
              {recommendedStalls.map((stall) => (
                <button
                  key={stall.name}
                  type="button"
                  onClick={() => handleSelectSearch(stall.name)}
                  className="w-full text-left px-2 py-1 rounded-lg hover:bg-muted/60 transition-colors flex items-center justify-between gap-2"
                >
                  <span className="text-xs text-foreground truncate">
                    {stall.name}
                  </span>
                  <span className="px-1.5 py-0.5 rounded bg-muted text-[10px] text-muted-foreground flex-shrink-0">
                    {stall.location}
                  </span>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Mobile Menu Dropdown */}
      {mobileMenuOpen && (
        <div className="md:hidden border-t border-border bg-background px-6 py-4 flex flex-col gap-4 text-sm">
          {authControls}
          <Link
            to="/food"
            onClick={() => setMobileMenuOpen(false)}
            className="text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            Discover
          </Link>
        </div>
      )}
    </nav>
  );
}