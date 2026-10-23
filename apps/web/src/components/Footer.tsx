import { Link } from "react-router-dom";

export default function Footer() {
  return (
    <footer className="border-t border-border py-10">
      <div className="max-w-7xl mx-auto px-6 flex flex-col md:flex-row items-center justify-between gap-4">
        <Link to="/" aria-label="NTUmmy home" className="flex items-center">
          <img
            src="/ntummy_logo.svg"
            alt="NTUmmy"
            className="h-11 w-auto -translate-y-1.5"
          />
        </Link>
        <p className="text-xs text-muted-foreground">Made by NTU students, for NTU students.</p>
        <div className="flex gap-6 text-xs text-muted-foreground">
          {["About", "Contribute", "Privacy"].map((l) => (
            <a key={l} href="#" className="hover:text-foreground transition-colors">
              {l}
            </a>
          ))}
        </div>
      </div>
    </footer>
  );
}