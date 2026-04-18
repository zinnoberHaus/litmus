# Copy-paste badge snippets

These are working snippets for every surface the badge ships to. Swap
`litmus.example.com` for your own Litmus server URL and `lme_a7k3fqxn2p`
for your metric's real embed token (see `GET /api/v1/metrics/{slug}` →
`embed_token`).

Full walkthrough with screenshots and gotchas: [`docs/badges.md`](../../docs/badges.md).

## GitHub README

```markdown
![Trust](https://litmus.example.com/embed/lme_a7k3fqxn2p/badge.svg)
```

Clickable, small variant suitable for a shields-style badge row:

```markdown
[![Trust](https://litmus.example.com/embed/lme_a7k3fqxn2p/badge.svg?size=small)](https://litmus.example.com/metrics/monthly_revenue)
```

Next to CI badges in shields.io style:

```markdown
![CI](https://img.shields.io/github/actions/workflow/status/owner/repo/ci.yml?style=for-the-badge)
![Trust](https://litmus.example.com/embed/lme_a7k3fqxn2p/badge.svg?style=for-the-badge)
```

## Notion

1. Type `/embed` on a page.
2. Paste this URL:

```
https://litmus.example.com/embed/lme_a7k3fqxn2p/badge.svg
```

## Slack unfurl

Post the metric URL (**not** the SVG URL) — Slack reads the OpenGraph tags
on `/embed/<token>.html` and renders a live preview:

```
Monthly revenue status: https://litmus.example.com/metrics/monthly_revenue
```

## Confluence (HTML macro)

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

## Email (inline image)

```html
<a href="https://litmus.example.com/metrics/monthly_revenue">
  <img
    alt="Litmus trust — Monthly Revenue"
    src="https://litmus.example.com/embed/lme_a7k3fqxn2p/badge.svg"
    height="36"
    style="border:0;display:block;"
  />
</a>
```

Gmail proxies and caches SVGs for up to 24h; Outlook on Windows blocks
external images by default. See `docs/badges.md` for the full email caveats.

## HTML / docs site

```html
<a href="https://litmus.example.com/metrics/monthly_revenue">
  <img
    alt="Litmus trust: Monthly Revenue"
    src="https://litmus.example.com/embed/lme_a7k3fqxn2p/badge.svg"
    height="36"
  />
</a>
```

## Size / colour / label cheatsheet

```
?size=small                     # 160×20 — READMEs
?size=medium                    # 275×36 — default
?size=large                     # 400×60 — landing heroes
?label=Revenue                  # override the main text
?color=4c1d95                   # accent hex without `#`
?style=for-the-badge            # shields.io-style upper-case pill
?size=small&style=for-the-badge # combine freely
```

All params are optional; invalid values fall back to sane defaults.
