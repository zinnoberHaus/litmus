"use client";

import { useState } from "react";

interface CopyButtonProps {
  text: string;
  /** Optional custom label (default "Copy"). */
  label?: string;
  /** Pin the button absolute to the top-right of a code block. */
  floating?: boolean;
  className?: string;
}

/**
 * Copy-to-clipboard button shared by install snippets and the badge gallery.
 * Keeps the "copied!" affordance for 1.5s so users know the click registered.
 */
export function CopyButton({
  text,
  label = "Copy",
  floating = false,
  className = "",
}: CopyButtonProps) {
  const [copied, setCopied] = useState(false);

  async function onClick() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Older browsers / non-secure contexts — fall back silently. The code
      // snippet itself stays visible so the user can select + copy manually.
      setCopied(false);
    }
  }

  const base =
    "inline-flex items-center gap-1.5 rounded-md border border-neutral-200 bg-white px-2 py-1 text-xs font-medium text-neutral-700 shadow-sm transition hover:border-neutral-300 hover:bg-neutral-50";
  const pos = floating ? "absolute right-2 top-2" : "";

  return (
    <button
      type="button"
      onClick={onClick}
      className={`${base} ${pos} ${className}`.trim()}
    >
      {copied ? "Copied" : label}
    </button>
  );
}
