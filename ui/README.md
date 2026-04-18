# Litmus UI

Web frontend for **Litmus** — the trust-and-approval layer for business metrics. Part of the OSS monorepo (MIT/Apache).

Built around the **three-audience** positioning from the v0.3 refactor (see `../REFACTOR_BLUEPRINT.md`):

> Canonical metric contracts for engineers, AI-answered questions for PMs, embeddable trust badges for everyone.

## Stack

- Next.js 15 (App Router)
- React 19
- TypeScript
- Tailwind CSS
- Zero chart/graph libraries — sparklines and lineage are hand-drawn SVG

## Getting started

```bash
cd ui
npm install
npm run dev
```

Then open:

- http://localhost:3000 — the landing page (three audiences, one spec)
- http://localhost:3000/metrics — the metric catalog
- http://localhost:3000/metrics/mrr — metric detail with an AI sidebar
- http://localhost:3000/install — install flow hub
- http://localhost:3000/install/dbt — dbt package walkthrough (primary path)
- http://localhost:3000/install/cli — standalone CLI
- http://localhost:3000/install/hosted — self-hosted docker-compose
- http://localhost:3000/install/slack — Slack sign-off + `/ask` setup
- http://localhost:3000/ask — standalone AI chat page
- http://localhost:3000/badge — badge gallery with copy-paste snippets
- http://localhost:3000/embed/mrr — raw SVG badge

## Directory layout

```
ui/
  app/
    layout.tsx                  — root shell (nav + footer)
    page.tsx                    — landing page (three-audience pitch)
    not-found.tsx               — app-router 404
    globals.css                 — tailwind entry
    metrics/
      page.tsx                  — catalog (empty-state hands users to /install)
      [id]/page.tsx             — metric detail + AI sidebar
    install/
      layout.tsx                — shared install-tabs chrome
      page.tsx                  — hub chooser (dbt / cli / hosted / slack)
      dbt/page.tsx              — dbt package walkthrough
      cli/page.tsx              — standalone CLI walkthrough
      hosted/page.tsx           — docker-compose self-host
      slack/page.tsx            — Slack webhook + signing-secret setup
    ask/page.tsx                — standalone AI chat
    badge/page.tsx              — badge gallery + embed snippets
    embed/[id]/route.ts         — server-rendered SVG badge
  components/
    Nav.tsx                     — top nav (org switcher hidden in OSS)
    Section.tsx                 — landing-section wrapper
    InstallTabs.tsx             — install-flow segmented control
    AskPanel.tsx                — reusable chat panel (sidebar + standalone)
    HeroBadgeDemo.tsx           — auto-polling badge for the landing hero
    CodeBlock.tsx               — snippet with floating copy button
    CopyButton.tsx              — clipboard helper
    SignoffChip.tsx             — Slack sign-off status chip
    TrustBadge.tsx              — existing pill
    TrustHistoryChart.tsx       — existing sparkline
    LineageGraph.tsx            — existing DAG
    ReconciliationPanel.tsx     — existing cross-source table
    WhyDidThisFail.tsx          — existing AI explanation panel
  lib/
    api.ts                      — live Litmus API client with fixture fallback
    ask.ts                      — /api/v1/ask helper (mocked in dev until task #54)
    fixtures.ts                 — demo-mode data for MRR/MAU/Churn
```

## What's real vs mocked

| Piece                     | Status                                                |
|---------------------------|-------------------------------------------------------|
| Catalog + detail          | Real (API-backed) with fixture fallback               |
| Trust history / lineage   | Real rendering, data from API or fixtures             |
| `/embed/[id]` SVG badge   | Real — proxies the API or falls back to local SVG     |
| Landing + install flow    | Static copy, quoted from `../docs/positioning.md`     |
| `<AskPanel>` chat         | UI real; `/api/v1/ask` endpoint still being built (#54) — `lib/ask.ts` returns a mocked response in dev |
| Slack sign-off chip       | UI real; sign-off pipeline being built (#52)          |
| Auth / SSO / org switcher | Out of scope for OSS (Cloud wedge, v0.5)              |

## Scripts

- `npm run dev` — dev server on port 3000
- `npm run build` — production build (run with `NODE_ENV=production` if your shell has `NODE_ENV=development` set)
- `npm run start` — run the production build
- `npm run typecheck` — TypeScript-only check (no emit)

## License

Same license as the root Litmus repo (see `../LICENSE`).
