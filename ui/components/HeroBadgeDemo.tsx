"use client";

/**
 * HeroBadgeDemo — small auto-polling badge for the landing hero.
 *
 * We already ship a server route at `/embed/[id]` that returns an SVG (either
 * proxied from the API or rendered locally from fixtures). The hero embeds
 * that route as an `<img>` so the landing shows a *real* badge — not a
 * mockup — and demonstrates the viral-loop mechanic without any extra state.
 *
 * The refresh interval is 60s by default. We also expose the fallback states
 * (trusted / review / broken / grey) as a tiny gallery beneath the live
 * badge so visitors see the full palette.
 */

import { useEffect, useState } from "react";

interface HeroBadgeDemoProps {
  /** Existing fixture id that the `/embed/[id]` route understands. */
  metricId?: string;
  /** Milliseconds between cache-busting refreshes. */
  pollMs?: number;
}

export function HeroBadgeDemo({
  metricId = "mrr",
  pollMs = 60_000,
}: HeroBadgeDemoProps) {
  // Bust the image cache periodically so viewers see the badge "tick" —
  // mirroring what a production Litmus instance would look like on someone's
  // Notion page.
  const [tick, setTick] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setTick(Date.now()), pollMs);
    return () => clearInterval(id);
  }, [pollMs]);

  const src = `/embed/${metricId}?t=${tick}`;

  return (
    <div className="flex flex-col items-start gap-4">
      <div className="flex items-center gap-3 rounded-xl border border-neutral-200 bg-white p-4 shadow-sm">
        <span className="text-xs font-medium text-neutral-500">
          Live badge:
        </span>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={src}
          alt="Litmus live trust badge"
          className="h-6"
          // Height matches the md size the API ships by default.
        />
        <span className="ml-1 text-[11px] text-neutral-400">
          refreshes every {Math.round(pollMs / 1000)}s
        </span>
      </div>
      <StatusGallery />
    </div>
  );
}

function StatusGallery() {
  // Hand-rendered SVG pills so the gallery works even if the embed route is
  // unreachable. Same colors as the server-rendered badge.
  const states: {
    label: string;
    fill: string;
    tone: string;
  }[] = [
    { label: "trusted", fill: "#16a34a", tone: "green" },
    { label: "review", fill: "#ca8a04", tone: "yellow" },
    { label: "broken", fill: "#dc2626", tone: "red" },
    { label: "unknown", fill: "#737373", tone: "neutral" },
  ];
  return (
    <div className="flex flex-wrap items-center gap-2 text-[11px] text-neutral-500">
      <span className="mr-1">Badge states:</span>
      {states.map((s) => (
        <MiniBadge key={s.label} label={s.label} fill={s.fill} />
      ))}
    </div>
  );
}

function MiniBadge({ label, fill }: { label: string; fill: string }) {
  const leftText = "litmus";
  const leftW = 56;
  const rightW = Math.max(60, label.length * 7 + 16);
  const total = leftW + rightW;
  const height = 22;
  return (
    <svg
      width={total}
      height={height}
      viewBox={`0 0 ${total} ${height}`}
      role="img"
      aria-label={`litmus ${label}`}
      className="overflow-hidden rounded"
    >
      <rect width={leftW} height={height} fill="#1f2937" />
      <rect x={leftW} width={rightW} height={height} fill={fill} />
      <g
        fill="#fff"
        textAnchor="middle"
        fontFamily="ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,sans-serif"
        fontSize="11"
      >
        <text x={leftW / 2} y={15}>
          {leftText}
        </text>
        <text x={leftW + rightW / 2} y={15}>
          {label}
        </text>
      </g>
    </svg>
  );
}
