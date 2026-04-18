# Embed a Litmus trust badge

One SVG, every surface. This guide covers everything between `GET
/embed/<token>/badge.svg` and a live badge rendered in your README, Notion
page, Slack channel, Confluence space, or marketing email.

> **Every rendered badge is a backlink.** Set `LITMUS_PUBLIC_URL` on your
> Litmus server and the badge wraps in an `<a xlink:href>` that links back
> to the metric detail page. Notion strips the anchor, but the `<title>`
> and `<desc>` text breadcrumbs stay — you always get attribution.

---

## Get a badge URL

Every metric has a stable embed token. Grab it from the catalog:

```bash
curl -s https://litmus.example.com/api/v1/metrics/monthly_revenue \
  | jq -r '.embed_token'
# lme_a7k3fqxn2p
```

Your badge URL is:

```
https://litmus.example.com/embed/lme_a7k3fqxn2p/badge.svg
```

That URL is **safe to embed anywhere**. It never returns an HTTP error — a
deleted metric renders a grey "Unknown" pill so third-party embeds don't
break. CORS is wide-open (`Access-Control-Allow-Origin: *`), cache headers
are set for 10 minutes by default (`LITMUS_EMBED_CACHE_SECONDS`).

---

## shields.io-style query params

Every badge accepts these query-string overrides. Anything invalid falls back
to the default — the never-404 contract extends to parameters.

| Param | Values | Default | Notes |
|---|---|---|---|
| `size` | `small`, `medium`, `large` (aliases: `sm`, `md`, `lg`) | `medium` | 160×20 / 275×36 / 400×60. Compact for READMEs, hero for landing pages. |
| `label` | any string | metric name | Override the main text. `?label=Revenue`. |
| `color` | hex without `#`, e.g. `4c1d95` | status-derived | 3 or 6 digits. Status colour returns if invalid. |
| `style` | `flat`, `for-the-badge` | `flat` | `for-the-badge` is the upper-case shields.io look — for CI/badge rows. |

### Cheatsheet

```
# Compact README badge
https://litmus.example.com/embed/<token>/badge.svg?size=small

# Hero badge for a landing page
https://litmus.example.com/embed/<token>/badge.svg?size=large

# Custom label + brand colour
https://litmus.example.com/embed/<token>/badge.svg?label=Revenue&color=4c1d95

# shields.io-compatible layout (sits next to CI badges)
https://litmus.example.com/embed/<token>/badge.svg?style=for-the-badge
```

---

## Platform guides

### GitHub README

Drop the URL into a standard markdown image tag:

```markdown
![Trust](https://litmus.example.com/embed/lme_a7k3fqxn2p/badge.svg)
```

Or wrap in a link so clicks jump to the metric page (GitHub honours the
anchor — Notion/Slack don't, but the badge's own `<a xlink:href>` works
inside SVG-capable renderers):

```markdown
[![Trust](https://litmus.example.com/embed/lme_a7k3fqxn2p/badge.svg?size=small)](https://litmus.example.com/metrics/monthly_revenue)
```

Mixing with shields.io badges in a badge row:

```markdown
![CI](https://img.shields.io/github/actions/workflow/status/owner/repo/ci.yml)
![Trust](https://litmus.example.com/embed/lme_a7k3fqxn2p/badge.svg?style=for-the-badge)
```

### Notion

Notion's `/embed` block renders SVGs from any URL. Paste the badge URL
directly into a page:

1. Type `/embed` in a Notion page.
2. Paste the full badge URL: `https://litmus.example.com/embed/<token>/badge.svg`.
3. Notion fetches and renders the SVG live on every page load.

Notion **strips the anchor** inside the SVG, so clicks won't navigate — but
the `<title>` tooltip shows on hover, and the `<desc>` breadcrumb carries
the metric URL as text (screen readers announce it).

### Slack

Slack doesn't embed raw SVGs in messages — instead, post the **metric page
URL** and Slack unfurls it into a preview card powered by the OpenGraph
tags on `/embed/<token>.html`:

```
Check out monthly revenue: https://litmus.example.com/metrics/monthly_revenue
```

Slack's crawler reads `og:title`, `og:description`, `og:image`, and
`og:url` from the page, and renders a card with the live badge as the
image. The server emits these tags on every share-card response, so
unfurl works out-of-the-box.

If your Slack workspace hasn't seen your Litmus domain before, unfurl is
disabled until an admin adds it via **Customize Slack → Integrations →
Allowed domains**.

### Confluence

Confluence's **HTML macro** (requires the HTML macro to be enabled for
your space) renders the badge:

```
{html}
<a href="https://litmus.example.com/metrics/monthly_revenue">
  <img
    alt="Litmus trust — Monthly Revenue"
    src="https://litmus.example.com/embed/lme_a7k3fqxn2p/badge.svg"
    height="36"
  />
</a>
{html}
```

For spaces without the HTML macro, use the **Iframe macro**:

```
{iframe:src=https://litmus.example.com/embed/lme_a7k3fqxn2p/badge.svg|width=300|height=40|frameborder=0}
```

The iframe keeps the backlink clickable, which the plain markdown image
macro does not.

### Email

Inline the SVG in an `<img src="...">`:

```html
<a href="https://litmus.example.com/metrics/monthly_revenue">
  <img
    alt="Litmus trust — Monthly Revenue"
    src="https://litmus.example.com/embed/lme_a7k3fqxn2p/badge.svg"
    height="36"
  />
</a>
```

**Caveat:** email clients cache images aggressively and inconsistently.
Gmail proxies images through its own cache and may hold a stale badge for
24h+. Outlook often blocks external images by default. For mission-critical
status, don't rely on email embeds — link to the metric page and let the
recipient click through.

Some clients (Outlook 2007–2019 on Windows) don't render SVG at all. If
you're sending to a known-Outlook audience, use `?style=for-the-badge` and
serve through a PNG conversion proxy of your choice.

### GitHub Pages / Jekyll / Docusaurus / MkDocs

Standard markdown image or HTML — both work:

```markdown
![Trust](https://litmus.example.com/embed/lme_a7k3fqxn2p/badge.svg)
```

```html
<img src="https://litmus.example.com/embed/lme_a7k3fqxn2p/badge.svg" alt="Trust">
```

Static-site builds fetch the SVG at render time, so the first page load
after a deploy shows the latest status without a rebuild.

---

## The viral loop

Set `LITMUS_PUBLIC_URL=https://your-litmus-server.com` on the Litmus
server and every badge wraps in an `<a xlink:href>` pointing at
`/metrics/<slug>`. In renderers that honour SVG anchors (Confluence
iframe, GitHub Pages, HTML docs, self-hosted dashboards), clicks on the
badge jump to the live metric detail page.

Renderers that strip the anchor (Notion, most email clients) still expose:

- The SVG `<title>` "Powered by Litmus — click for full metric detail"
  as a hover tooltip.
- The SVG `<desc>` containing the canonical metric URL, so screen readers
  and text-stripped embeds carry the breadcrumb.

No tracking pixel, no analytics beacon — the loop is the URL.

---

## Pre-built examples

See `examples/badges/index.html` for a visual QA grid of every size,
every status, every style variant. Open it in a browser and you'll see
the badge render exactly as Notion, Confluence, and GitHub render it.

For copy-paste snippets with live previews, visit `/badge` on your Litmus
UI — it's the same gallery, wired up to your actual catalog.
