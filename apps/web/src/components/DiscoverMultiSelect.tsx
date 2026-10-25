import { useEffect, useRef, useState, type ReactNode } from "react";
import { ChevronDown, X } from "lucide-react";

type Props = {
  id: string;
  label: string;
  placeholder: string;
  icon: ReactNode;
  options: string[];
  selected: string[];
  onChange: (values: string[]) => void;
};

export default function DiscoverMultiSelect({ id, label, placeholder, icon, options, selected, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    function closeOutside(event: PointerEvent) {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    }
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
        triggerRef.current?.focus();
      }
    }
    document.addEventListener("pointerdown", closeOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  function toggle(value: string) {
    onChange(selected.includes(value) ? selected.filter((item) => item !== value) : [...selected, value]);
  }

  return (
    <div ref={containerRef} className="min-w-0">
      <span id={`${id}-label`} className="mb-2 flex items-center gap-2 text-sm font-semibold">{icon} {label}</span>
      <div className="relative">
        <button ref={triggerRef} type="button" aria-labelledby={`${id}-label`} aria-expanded={open} aria-controls={`${id}-options`} onClick={() => setOpen((value) => !value)} className="flex w-full cursor-pointer items-center justify-between gap-2 rounded-xl border border-border bg-background px-3 py-3 text-left text-sm text-foreground focus-visible:outline-2 focus-visible:outline-primary">
          <span>{selected.length ? `${selected.length} selected` : placeholder}</span>
          <ChevronDown size={16} aria-hidden="true" className={`shrink-0 transition-transform ${open ? "rotate-180" : ""}`} />
        </button>
        {open && (
          <div id={`${id}-options`} role="group" aria-labelledby={`${id}-label`} className="absolute left-0 right-0 z-20 mt-2 overflow-hidden rounded-xl border border-border bg-card shadow-lg">
            <div className="flex items-center justify-between gap-2 border-b border-border px-3 py-3">
              <span className="text-xs text-muted-foreground">Choose as many as you like</span>
              <button type="button" aria-label={`Clear ${label.toLowerCase()}`} onClick={() => onChange([])} disabled={selected.length === 0} className="shrink-0 cursor-pointer text-xs font-semibold text-primary disabled:cursor-default disabled:opacity-40">Clear</button>
            </div>
            <div className="max-h-56 overflow-y-auto overscroll-contain p-1">
              {options.map((value) => (
                <label key={value} className={`flex cursor-pointer items-center gap-2 rounded-lg px-3 py-2.5 text-sm ${selected.includes(value) ? "bg-primary/5 font-semibold text-primary" : "text-foreground hover:bg-muted"}`}>
                  <input type="checkbox" checked={selected.includes(value)} onChange={() => toggle(value)} className="h-4 w-4 shrink-0 accent-primary" />
                  <span className="min-w-0 break-words">{value}</span>
                </label>
              ))}
            </div>
            <div className="border-t border-border p-2">
              <button type="button" aria-label={`Done choosing ${label.toLowerCase()}`} onClick={() => { setOpen(false); triggerRef.current?.focus(); }} className="w-full cursor-pointer rounded-lg bg-primary px-3 py-2 text-xs font-semibold text-primary-foreground hover:opacity-90">Done</button>
            </div>
          </div>
        )}
      </div>
      {selected.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5" aria-label={`Selected ${label.toLowerCase()}`}>
          {selected.map((value) => (
            <button key={value} type="button" onClick={() => toggle(value)} aria-label={`Remove ${value}`} className="flex max-w-full cursor-pointer items-center gap-1 rounded-full bg-primary/5 px-2.5 py-1.5 text-left text-xs font-semibold text-primary hover:bg-primary/10 focus-visible:outline-2 focus-visible:outline-primary">
              <span className="min-w-0 break-words">{value}</span><X size={12} aria-hidden="true" className="shrink-0" />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
