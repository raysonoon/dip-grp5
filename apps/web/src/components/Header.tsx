import { useState } from "react";
import { Link } from "react-router-dom";
import { Menu, Utensils, X } from "lucide-react";

export default function Header({ fixed = false }: { fixed?: boolean }) {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

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
          {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
        </button>
      </div>

      {mobileMenuOpen && (
        <div className="md:hidden border-t border-border bg-background px-6 py-4 flex flex-col gap-4 text-sm">
          <button className="text-sm text-muted-foreground hover:text-foreground transition-colors text-left">
            Sign In
          </button>
          <Link
            to="/food"
            className="text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            Discover
          </Link>
        </div>
      )}
    </nav>
  );
}