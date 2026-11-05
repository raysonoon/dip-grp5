import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Merge conditional class names and let later Tailwind utilities win.
 *
 * cn("px-2", isLarge && "px-4", "text-primary") → "px-4 text-primary"
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
