import { useEffect, useRef, useState, type ReactNode } from "react";
import { Check, ChevronDown } from "lucide-react";

type Option = {
  value: string;
  label: string;
};

type Props = {
  id: string;
  label: string;
  icon?: ReactNode;
  options: Option[];
  value: string;
  onChange: (value: string) => void;
};

export default function SingleSelect({ id, label, icon, options, value, onChange }: Props) {
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

  const selected = options.find((option) => option.value === value);

  return (
    <div ref={containerRef} className="relative flex w-full sm:w-auto">
      <button
        ref={triggerRef}
        type="button"
        aria-label={label}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={`${id}-options`}
        onClick={() => setOpen((current) => !current)}
        className="flex w-full cursor-pointer items-center justify-center gap-2 rounded-xl border border-border bg-background px-3.5 py-2.5 text-left text-sm font-semibold leading-5 text-foreground focus-visible:outline-2 focus-visible:outline-primary sm:w-auto"
      >
        <span className="flex min-w-0 items-center gap-2">
          {icon}
          <span className="truncate">{selected?.label ?? label}</span>
        </span>
        <ChevronDown
          size={16}
          aria-hidden="true"
          className={`mt-0.5 shrink-0 transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open && (
        <div
          id={`${id}-options`}
          role="listbox"
          aria-label={label}
          className="absolute left-0 right-0 top-full z-20 mt-2 overflow-hidden rounded-xl border border-border bg-card p-1 shadow-lg sm:min-w-full"
        >
          {options.map((option) => {
            const isSelected = option.value === value;
            return (
              <button
                key={option.value}
                type="button"
                role="option"
                aria-selected={isSelected}
                onClick={() => {
                  onChange(option.value);
                  setOpen(false);
                  triggerRef.current?.focus();
                }}
                className={`flex w-full cursor-pointer items-center justify-between gap-2 rounded-lg px-3 py-2.5 text-left text-sm ${
                  isSelected
                    ? "bg-primary/5 font-semibold text-primary"
                    : "text-foreground hover:bg-muted"
                }`}
              >
                <span className="min-w-0">{option.label}</span>
                {isSelected && <Check size={14} aria-hidden="true" className="mt-1 shrink-0" />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
