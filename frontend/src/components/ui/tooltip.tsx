import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface TooltipProps {
  text: string;
  children: ReactNode;
  className?: string;
}

/**
 * Lightweight CSS-only tooltip — no JS, no portal.
 * Shows above the trigger by default; falls back gracefully if clipped.
 */
export function Tooltip({ text, children, className }: TooltipProps) {
  return (
    <span className={cn("group relative inline-block cursor-help", className)}>
      {children}
      <span
        className={cn(
          // Positioning: above the trigger, left-aligned
          "pointer-events-none absolute bottom-full left-0 z-50 mb-2 w-64",
          // Solid dark background — readable on any page background
          "rounded-md bg-neutral-900 px-3 py-2 text-xs leading-relaxed text-neutral-50 shadow-lg",
          // Show on hover
          "opacity-0 group-hover:opacity-100",
          "transition-opacity duration-150",
        )}
      >
        {text}
        {/* Arrow */}
        <span className="absolute left-3 top-full h-0 w-0 border-x-4 border-x-transparent border-t-4 border-t-neutral-900" />
      </span>
    </span>
  );
}