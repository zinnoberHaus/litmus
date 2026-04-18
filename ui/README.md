# Litmus UI

Web frontend for the **Litmus metric catalog** (part of the OSS repo, MIT/Apache licensed with the rest of Litmus). Built for the 0.2 pivot from pure CLI to *hosted catalog + embeddable trust badges*.

This is a scaffold — every piece of data on screen today comes from local fixtures in `lib/fixtures.ts`. Wiring to the Python API is the next step.

## Stack

- Next.js 15 (App Router)
- React 19
- TypeScript
- Tailwind CSS
- Zero chart/graph libraries — sparklines and lineage are hand-drawn SVG

Dependencies are intentionally minimal. No ESLint, no shadcn runtime, no recharts.

## Getting started

```bash
cd ui
npm install
npm run dev
```

Then open:

- http://localhost:3000 — the catalog (MRR, MAU, Churn)
- http://localhost:3000/metrics/mrr — the metric detail page (the "killer screen")
- http://localhost:3000/metrics/mau — warning example
- http://localhost:3000/metrics/churn — failing example + cross-source disagreement
- http://localhost:3000/embed/mrr — raw SVG trust badge (for Notion/Slack/READMEs)

## Directory layout

```
ui/
  app/
    layout.tsx                  — top-level shell (header/footer)
    page.tsx                    — catalog (list of metrics)
    globals.css                 — tailwind entry
    metrics/[id]/page.tsx       — metric detail (definition, trust history, lineage, reconciliation)
    embed/[id]/route.ts         — server-rendered SVG badge, Content-Type: image/svg+xml
  components/
    TrustBadge.tsx              — green/yellow/red pill
    TrustHistoryChart.tsx       — SVG sparkline w/ pass/warn/fail bands
    LineageGraph.tsx            — SVG left-to-right DAG
    ReconciliationPanel.tsx     — warehouse vs Looker vs Tableau table
  lib/
    fixtures.ts                 — all dummy data lives here
  package.json
  tsconfig.json
  tailwind.config.ts
  postcss.config.mjs
  next.config.mjs
```

## What's real vs stubbed

| Piece | Status |
|-------|--------|
| Catalog list | Stubbed (3 metrics in `lib/fixtures.ts`) |
| Metric detail layout | Real — final shape |
| Trust badge colors + semantics | Real |
| Trust history sparkline | Real renderer, stubbed data |
| Lineage graph | Real renderer, stubbed data, *naive* left-to-right layout (swap for dagre/elkjs later) |
| Cross-source reconciliation | Real component, stubbed rows |
| `/embed/:id` SVG badge | Real SVG output, stubbed status |
| Auth / multi-tenant | Not in scope for scaffold |
| API layer | Not wired |

## Where real API integration will go

Every read happens through two synchronous functions at the bottom of `lib/fixtures.ts`:

```ts
listMetrics(): Metric[]
getMetric(id: string): Metric | null
```

When the Python API lands, turn these into `async` functions that call `fetch(...)`. The `Metric` interface is the contract — keep the shape stable and the components above will not need to change.

Suggested wiring:

1. Add `API_BASE` (env var `LITMUS_API_URL` on the server).
2. Make `listMetrics` / `getMetric` `async` and `await fetch(\`${API_BASE}/metrics\`)`.
3. Convert page components to `async` where needed (already the case for `metrics/[id]`).
4. For the embed route, the server handler in `app/embed/[id]/route.ts` already runs on the Node runtime — fetch from the API there and render the SVG from the live trust status.

## Scripts

- `npm run dev` — dev server on port 3000
- `npm run build` — production build
- `npm run start` — run the production build
- `npm run typecheck` — TypeScript-only check (no emit)

## License

Same license as the root Litmus repo (see `../LICENSE`).
