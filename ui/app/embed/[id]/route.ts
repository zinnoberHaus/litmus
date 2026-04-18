import { getApiBase, getEmbedToken, getMetric } from "@/lib/api";

/**
 * `/embed/:id` returns a server-rendered SVG trust badge suitable for
 * embedding in Notion, Slack, GitHub READMEs, etc.
 *
 * Resolution strategy (in order):
 *   1. If the Litmus API is reachable, look up the metric's embed token and
 *      proxy the API's `/embed/<token>/badge.svg` — single source of truth
 *      for what "trusted / review / broken" looks like.
 *   2. Otherwise render a local fallback pill using the fixture data. This
 *      keeps the scaffold demo-usable without any backend running.
 *
 * We never 404 — third-party surfaces (Notion, Confluence) render broken
 * images badly, and the whole point is to be unobtrusive.
 */

const STATUS_FILL: Record<string, string> = {
  pass: "#16a34a",
  warn: "#ca8a04",
  fail: "#dc2626",
};

const STATUS_LABEL: Record<string, string> = {
  pass: "trusted",
  warn: "review",
  fail: "broken",
};

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

interface RouteContext {
  params: Promise<{ id: string }>;
}

async function proxyFromApi(id: string): Promise<Response | null> {
  const base = getApiBase();
  if (!base) return null;
  const token = await getEmbedToken(id);
  if (!token) return null;
  try {
    const upstream = await fetch(`${base}/embed/${token}/badge.svg`, {
      cache: "no-store",
    });
    if (!upstream.ok) return null;
    const svg = await upstream.text();
    return new Response(svg, {
      headers: {
        "Content-Type": "image/svg+xml; charset=utf-8",
        "Cache-Control": "public, max-age=60, s-maxage=60",
      },
    });
  } catch {
    return null;
  }
}

function renderFallbackSvg(name: string, status: string, label: string): string {
  const fill = STATUS_FILL[status] ?? STATUS_FILL.warn;
  const leftText = "litmus";
  const rightText = label;
  const leftW = Math.max(56, leftText.length * 7 + 14);
  const rightW = Math.max(60, rightText.length * 7 + 16);
  const total = leftW + rightW;
  const height = 24;
  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="${total}" height="${height}" viewBox="0 0 ${total} ${height}" role="img" aria-label="Litmus: ${name} — ${label}">
  <title>Litmus: ${name} — ${label}</title>
  <linearGradient id="s" x2="0" y2="100%">
    <stop offset="0" stop-color="#fff" stop-opacity=".2"/>
    <stop offset="1" stop-opacity=".08"/>
  </linearGradient>
  <clipPath id="c"><rect width="${total}" height="${height}" rx="4" ry="4"/></clipPath>
  <g clip-path="url(#c)">
    <rect width="${leftW}" height="${height}" fill="#1f2937"/>
    <rect x="${leftW}" width="${rightW}" height="${height}" fill="${fill}"/>
    <rect width="${total}" height="${height}" fill="url(#s)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,sans-serif" font-size="12">
    <text x="${leftW / 2}" y="16">${leftText}</text>
    <text x="${leftW + rightW / 2}" y="16">${rightText}</text>
  </g>
</svg>`;
}

export async function GET(_req: Request, ctx: RouteContext) {
  const { id } = await ctx.params;

  const proxied = await proxyFromApi(id);
  if (proxied) return proxied;

  const metric = await getMetric(id);
  const status = metric?.trustStatus ?? "warn";
  const label = metric ? STATUS_LABEL[status] : "unknown";
  const name = metric?.name ?? id;
  const svg = renderFallbackSvg(name, status, label);

  return new Response(svg, {
    headers: {
      "Content-Type": "image/svg+xml; charset=utf-8",
      "Cache-Control": "public, max-age=60, s-maxage=60",
    },
  });
}
