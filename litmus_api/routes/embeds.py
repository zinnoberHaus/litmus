from __future__ import annotations

from html import escape

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import desc
from sqlalchemy.orm import Session

from litmus_api.config import Settings, get_settings
from litmus_api.db import get_session
from litmus_api.embed_svg import render_badge_svg
from litmus_api.models import EmbedKey, Metric, Run

router = APIRouter(tags=["embeds"])


def _cache_headers(settings: Settings) -> dict[str, str]:
    cache = (
        f"public, max-age={settings.embed_cache_seconds}, "
        f"s-maxage={settings.embed_cache_seconds}"
    )
    return {
        "Cache-Control": cache,
        "Access-Control-Allow-Origin": "*",
    }


def _metric_url(settings: Settings, slug: str | None, token: str) -> str | None:
    """Public URL for a metric detail page, used as the badge backlink.

    Prefer `/metrics/<slug>` when we know the slug — it's the human-readable
    URL we want indexed. Falls back to `/embed/<token>.html` (the OG card)
    when we only have a token (e.g. unknown-token safe fallback). Returns
    ``None`` if ``LITMUS_PUBLIC_URL`` is unset — no backlink is better than a
    broken one.
    """
    if not settings.public_url:
        return None
    if slug:
        return f"{settings.public_url}/metrics/{slug}"
    return f"{settings.public_url}/embed/{token}.html"


def _unknown_svg(
    settings: Settings,
    token: str,
    *,
    size: str | None,
    label: str | None,
    color: str | None,
    style: str | None,
) -> Response:
    svg = render_badge_svg(
        metric_name=label or "unknown metric",
        status="unknown",
        size=size,
        label=label,
        color=color,
        style=style,
        metric_url=_metric_url(settings, None, token),
    )
    return Response(
        content=svg,
        media_type="image/svg+xml; charset=utf-8",
        headers=_cache_headers(settings),
    )


@router.get("/embed/{token}/badge.svg")
def embed_badge(
    token: str,
    size: str | None = Query(
        default=None,
        description="One of small|medium|large (aliases: sm|md|lg). Default: medium.",
    ),
    label: str | None = Query(
        default=None,
        description="Override the metric-name label. Defaults to the metric's name.",
    ),
    color: str | None = Query(
        default=None,
        description="Accent colour as hex without `#` (e.g. 4c1d95). "
        "Invalid values fall back to the status-derived palette.",
    ),
    style: str | None = Query(
        default=None,
        description="`flat` (default) or `for-the-badge` for a shields.io-style layout.",
    ),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Response:
    """Render the embeddable trust badge SVG.

    Never 404s — an unknown/revoked token returns a grey "Unknown" pill so
    third-party embeds (README, Notion, Slack) stay rendered even when the
    metric is deleted on the Litmus side.

    shields.io-compatible query params:

    - ``?size=small|medium|large`` — 160×20 (readmes) / 275×36 (default) / 400×60 (hero)
    - ``?label=Revenue`` — override the metric-name text
    - ``?color=4c1d95`` — override the accent colour (hex, no `#`)
    - ``?style=flat|for-the-badge`` — shields.io-style layouts
    """
    key: EmbedKey | None = (
        session.query(EmbedKey).filter_by(token=token, revoked_at=None).one_or_none()
    )
    if key is None:
        return _unknown_svg(
            settings, token, size=size, label=label, color=color, style=style
        )

    metric: Metric | None = session.get(Metric, key.metric_id)
    if metric is None or metric.deleted_at is not None:
        return _unknown_svg(
            settings, token, size=size, label=label, color=color, style=style
        )

    latest: Run | None = (
        session.query(Run)
        .filter_by(metric_id=metric.id)
        .order_by(desc(Run.started_at))
        .first()
    )
    status = latest.status if latest else "unknown"
    trust_score = (
        float(latest.trust_score) if latest and latest.trust_score is not None else None
    )

    svg = render_badge_svg(
        metric_name=metric.name,
        status=status,
        trust_score=trust_score,
        size=size,
        label=label,
        color=color,
        style=style,
        metric_url=_metric_url(settings, metric.slug, token),
    )
    return Response(
        content=svg,
        media_type="image/svg+xml; charset=utf-8",
        headers=_cache_headers(settings),
    )


@router.get("/embed/{token}.html", response_class=HTMLResponse)
def embed_card(
    token: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    """Public share card for a metric — the OpenGraph surface for Slack unfurl.

    Slack (and Twitter, LinkedIn, iMessage) look for `og:*` + `twitter:*` tags
    when a link is posted, and render a preview card. We serve a minimal HTML
    page whose `og:image` is the live badge SVG, so any channel that gets the
    metric URL pasted gets a live trust preview.

    Never 404s — mirrors the badge contract.
    """
    key: EmbedKey | None = (
        session.query(EmbedKey).filter_by(token=token, revoked_at=None).one_or_none()
    )
    metric: Metric | None = None
    latest: Run | None = None
    if key is not None:
        metric = session.get(Metric, key.metric_id)
        if metric is not None and metric.deleted_at is None:
            latest = (
                session.query(Run)
                .filter_by(metric_id=metric.id)
                .order_by(desc(Run.started_at))
                .first()
            )

    metric_name = metric.name if metric else "Unknown metric"
    description = (
        metric.description
        if metric and metric.description
        else "Live trust badge powered by Litmus."
    )
    status = latest.status if latest else "unknown"
    status_copy = {
        "passed": "Trusted",
        "warning": "Review",
        "failed": "Broken",
        "error": "Error",
        "unknown": "Unknown",
    }.get(status, "Unknown")

    # OG image points at the SVG for the same token — cheap, always-live.
    svg_url_rel = f"/embed/{token}/badge.svg"
    svg_url_abs = (
        f"{settings.public_url}{svg_url_rel}" if settings.public_url else svg_url_rel
    )
    canonical_url = _metric_url(settings, metric.slug if metric else None, token) or (
        f"{settings.public_url}/embed/{token}.html" if settings.public_url else svg_url_rel
    )

    title = f"{metric_name} — {status_copy}"
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{escape(title)} · Litmus</title>
  <meta name="description" content="{escape(description)}">
  <meta property="og:type" content="website">
  <meta property="og:title" content="{escape(title)}">
  <meta property="og:description" content="{escape(description)}">
  <meta property="og:image" content="{escape(svg_url_abs, quote=True)}">
  <meta property="og:image:alt" content="Litmus trust badge for {escape(metric_name)}">
  <meta property="og:url" content="{escape(canonical_url, quote=True)}">
  <meta property="og:site_name" content="Litmus">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{escape(title)}">
  <meta name="twitter:description" content="{escape(description)}">
  <meta name="twitter:image" content="{escape(svg_url_abs, quote=True)}">
  <link rel="canonical" href="{escape(canonical_url, quote=True)}">
  <style>
    body {{ font: 15px/1.5 ui-sans-serif, system-ui, -apple-system, sans-serif;
            color: #111827; background: #f9fafb; margin: 0;
            display: flex; align-items: center; justify-content: center;
            min-height: 100vh; padding: 2rem; }}
    .card {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 16px;
             padding: 2rem; max-width: 640px; width: 100%;
             box-shadow: 0 1px 3px rgba(0,0,0,.04); }}
    h1 {{ font-size: 1.25rem; margin: 0 0 .5rem; }}
    p {{ margin: .25rem 0; color: #374151; }}
    .badge img {{ display: block; margin: 1rem 0; }}
    a {{ color: #4f46e5; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .muted {{ color: #6b7280; font-size: .875rem; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>{escape(metric_name)}</h1>
    <p>{escape(description)}</p>
    <div class="badge"><img src="{escape(svg_url_rel, quote=True)}" \
alt="Litmus trust badge for {escape(metric_name)}" height="36"></div>
    <p class="muted">Powered by <a href="{escape(canonical_url, quote=True)}">Litmus</a> \
— live trust badge. <a href="{escape(svg_url_rel, quote=True)}">View SVG</a>.</p>
  </div>
</body>
</html>"""
    return HTMLResponse(content=html, headers=_cache_headers(settings))
