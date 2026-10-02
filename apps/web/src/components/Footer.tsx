import { Utensils } from "lucide-react";

export default function Footer() {
  return (
    <footer className="border-t border-border py-10">
      <div className="max-w-7xl mx-auto px-6 flex flex-col md:flex-row items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-sm bg-primary flex items-center justify-center">
            <Utensils className="w-3 h-3 text-primary-foreground" />
          </div>
          <span className="text-sm font-bold font-display">NTUmmy</span>
        </div>
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