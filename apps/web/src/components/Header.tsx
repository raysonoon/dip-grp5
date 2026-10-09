import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { ChevronDown, LogOut, Menu, Utensils, X } from "lucide-react";
import { useAuth } from "../contexts/AuthContext";

export default function Header({ fixed = false }: { fixed?: boolean }) {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [accountMenuOpen, setAccountMenuOpen] = useState(false);
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

  return (
    <nav
      className={`${fixed ? "fixed top-0 left-0 right-0" : "sticky top-0"} z-40 w-full border-b border-border bg-background/80 sm:backdrop-blur-md`}
    >
      <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-sm bg-primary flex items-center justify-center">
            <Utensils className="w-4 h-4 text-primary-foreground" />
          </div>
          <span className="text-lg font-bold text-foreground font-display">
            NTUmmy
          </span>
        </Link>

        <div className="hidden md:flex items-center gap-3">
          {authControls}
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
          {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
        </button>
      </div>

      {mobileMenuOpen && (
        <div className="md:hidden border-t border-border bg-background px-6 py-4 flex flex-col gap-4 text-sm">
          {authControls}
          <Link
            to="/food"
            className="text-sm text-muted-foreground hover:text-foreground transition-colors"
            onClick={() => setMobileMenuOpen(false)}
          >
            Discover
          </Link>
        </div>
      )}
    </nav>
  );
}