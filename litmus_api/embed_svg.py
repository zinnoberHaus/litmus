"""SVG generator for the embeddable trust badge — the viral wedge.

Rendered output is a pill (sm / md / lg) with:
  - coloured status dot (or shields.io-style left/right split for ``for-the-badge``)
  - metric name (ellipsised; overridable via ``?label=``)
  - status label (Trusted / Review / Broken / Unknown; colour overridable via ``?color=``)
  - trust score, if known (suppressed on the ``small`` size — no room)
  - ``litmus`` wordmark on the right (+ tiny glyph on the large size)

Every rendered badge wraps in an ``<a xlink:href="...">`` pointing at the public
metric detail URL so README/Confluence renders are clickable — the viral loop.
Notion strips anchors but the ``<title>`` and ``<desc>`` text breadcrumbs stay.

Colours are locked to the same palette as ui/components/TrustBadge.tsx so the
Notion/Slack-embedded version matches the in-app card pixel for pixel.
"""

from __future__ import annotations

import re
from html import escape

_STATUS_COPY = {
    "passed": "Trusted",
    "warning": "Review",
    "failed": "Broken",
    "error": "Error",
    "unknown": "Unknown",
    # aliases accepted from upstream systems
    "pass": "Trusted",
    "warn": "Review",
    "fail": "Broken",
}

# (dot/accent, bg, ring) for each status — shared by all sizes.
_STATUS_COLOURS = {
    "passed": ("#16a34a", "#f0fdf4", "#bbf7d0"),
    "pass": ("#16a34a", "#f0fdf4", "#bbf7d0"),
    "warning": ("#ca8a04", "#fefce8", "#fde68a"),
    "warn": ("#ca8a04", "#fefce8", "#fde68a"),
    "failed": ("#dc2626", "#fef2f2", "#fecaca"),
    "fail": ("#dc2626", "#fef2f2", "#fecaca"),
    "error": ("#dc2626", "#fef2f2", "#fecaca"),
    "unknown": ("#6b7280", "#f9fafb", "#e5e7eb"),
}

# Size variants. Values tuned against the UI's /badge gallery so the hand-drawn
# preview (ui/app/badge/page.tsx) and the server-rendered SVG line up visually.
#
#   key    = URL query string accepted ("small", "sm", "medium", "md", ...)
#   height = total SVG height in px
#   radius = pill corner radius
#   dot_r  = status dot radius
#   pad_x  = left padding before the dot
#   name_f = name font size (px)
#   label_f = status label font size (px)
#   brand_f = "litmus" wordmark font size (px)
#   char_w = budget per char when estimating width
_SIZE_VARIANTS = {
    "small": {
        "height": 20,
        "radius": 4,
        "dot_r": 3,
        "pad_x": 8,
        "name_f": 10,
        "label_f": 10,
        "brand_f": 9,
        "char_w": 5.4,
        "min_width": 160,
    },
    "medium": {
        "height": 36,
        "radius": 8,
        "dot_r": 4,
        "pad_x": 12,
        "name_f": 13,
        "label_f": 12,
        "brand_f": 10,
        "char_w": 7.5,
        "min_width": 275,
    },
    "large": {
        "height": 60,
        "radius": 12,
        "dot_r": 6,
        "pad_x": 18,
        "name_f": 20,
        "label_f": 16,
        "brand_f": 12,
        "char_w": 10.5,
        "min_width": 400,
    },
}

# Aliases so ``?size=md`` and ``?size=medium`` both work. Invalid values silently
# fall back to the default ("medium") — the never-404 contract extends to params.
_SIZE_ALIASES = {
    "sm": "small",
    "s": "small",
    "small": "small",
    "md": "medium",
    "m": "medium",
    "medium": "medium",
    "default": "medium",
    "lg": "large",
    "l": "large",
    "large": "large",
    "xl": "large",
}

_STYLE_ALIASES = {
    "flat": "flat",
    "plastic": "flat",  # shields.io compat — no rounded-3d variant for MVP
    "for-the-badge": "for-the-badge",
    "for_the_badge": "for-the-badge",
    "ftb": "for-the-badge",
}

# Max chars we show before truncating the metric name, per size.
_NAME_MAX_CHARS = {"small": 18, "medium": 28, "large": 40}

_HEX_RE = re.compile(r"^[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?$")


def _normalise_size(size: str | None) -> str:
    if not size:
        return "medium"
    return _SIZE_ALIASES.get(size.strip().lower(), "medium")


def _normalise_style(style: str | None) -> str:
    if not style:
        return "flat"
    return _STYLE_ALIASES.get(style.strip().lower(), "flat")


def _normalise_color(color: str | None) -> str | None:
    """Accept 3-or-6-digit hex without the leading ``#``. Invalid → ``None``."""
    if color is None:
        return None
    c = color.strip().lstrip("#")
    if _HEX_RE.match(c):
        return f"#{c.lower()}"
    return None


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def _render_for_the_badge(
    *,
    left: str,
    right: str,
    accent: str,
    size_key: str,
    metric_name: str,
    metric_url: str | None,
    status_label: str,
) -> str:
    """shields.io ``for-the-badge`` variant — upper-case, two-tone, chunky.

    Matches the visual weight of the similar shields.io style so Litmus badges
    sit cleanly next to CI/coverage shields in a README row.
    """
    variant = _SIZE_VARIANTS[size_key]
    height = variant["height"]
    # Upper-case per shields convention.
    left_u = left.upper()
    right_u = right.upper()
    char_w = variant["char_w"]
    left_w = max(70, int(len(left_u) * char_w) + 24)
    right_w = max(80, int(len(right_u) * char_w) + 24)
    total = left_w + right_w
    font_name = (
        'ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'
    )
    font_size = max(9, int(variant["name_f"] * 0.85))
    name_esc = escape(metric_name)
    label_esc = escape(status_label)
    left_esc = escape(left_u)
    right_esc = escape(right_u)

    body = f"""<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" \
width="{total}" height="{height}" viewBox="0 0 {total} {height}" role="img" \
aria-label="litmus trust badge for {name_esc}: {label_esc}">
  <title>Powered by Litmus — click for full metric detail</title>
  <desc>{name_esc} — {label_esc}. {escape(metric_url or "")}</desc>
  <rect width="{left_w}" height="{height}" fill="#1f2937"/>
  <rect x="{left_w}" width="{right_w}" height="{height}" fill="{accent}"/>
  <g fill="#ffffff" text-anchor="middle" font-family='{font_name}' \
font-size="{font_size}" font-weight="700" letter-spacing="1">
    <text x="{left_w / 2:.1f}" y="{height / 2 + font_size / 3:.1f}">{left_esc}</text>
    <text x="{left_w + right_w / 2:.1f}" y="{height / 2 + font_size / 3:.1f}">{right_esc}</text>
  </g>
</svg>"""
    return _wrap_anchor(body, metric_url)


def _wrap_anchor(svg: str, metric_url: str | None) -> str:
    """Wrap the SVG in an ``<a xlink:href>`` if we have a backlink URL.

    Placing the anchor *inside* the SVG (rather than around it) keeps the
    markup valid when consumers paste the SVG body directly into HTML —
    e.g. inlined into a dashboard instead of used as an ``<img src=>``.
    """
    if not metric_url:
        return svg
    # Inject the anchor right after the opening <svg ...> tag so the whole
    # visible area becomes clickable. Uses xlink:href for SVG 1.1 compatibility
    # (GitHub + Notion render better with xlink than bare href on <a>).
    open_end = svg.find(">")
    if open_end == -1:
        return svg
    head = svg[: open_end + 1]
    tail = svg[open_end + 1 :]
    # Close </a> just before </svg>.
    close_idx = tail.rfind("</svg>")
    if close_idx == -1:
        return svg
    inner = tail[:close_idx]
    return (
        f'{head}<a xlink:href="{escape(metric_url, quote=True)}" '
        f'target="_blank" rel="noopener">{inner}</a></svg>'
    )


def render_badge_svg(
    *,
    metric_name: str,
    status: str,
    trust_score: float | None = None,
    size: str | None = None,
    label: str | None = None,
    color: str | None = None,
    style: str | None = None,
    metric_url: str | None = None,
) -> str:
    """Render the trust badge SVG.

    Args:
        metric_name: Human name of the metric (used as the main label).
        status: One of ``passed|warning|failed|error|unknown`` (aliases accepted).
        trust_score: 0–1 float rendered as a percentage suffix; omitted on ``small``.
        size: ``small|medium|large`` (aliases: sm/md/lg, s/m/l). Invalid → medium.
        label: Override the metric-name label. Handy for ``?label=Revenue``.
        color: Override the accent colour. Hex without ``#`` (e.g. ``4c1d95``).
            Invalid values silently fall back to the status-derived palette —
            the never-404 contract extends to query params.
        style: ``flat`` (default) or ``for-the-badge`` (shields.io-compatible).
        metric_url: Where the badge links to when clicked. Optional; the route
            layer resolves this from ``LITMUS_PUBLIC_URL``.

    Returns:
        An SVG string ready to serve as ``image/svg+xml``.
    """
    size_key = _normalise_size(size)
    style_key = _normalise_style(style)
    variant = _SIZE_VARIANTS[size_key]

    status_key = (status or "unknown").lower()
    dot, bg, ring = _STATUS_COLOURS.get(status_key, _STATUS_COLOURS["unknown"])
    status_label = _STATUS_COPY.get(
        status_key, status.title() if status else "Unknown"
    )

    # Shields.io-style overrides.
    accent = _normalise_color(color) or dot
    # If the caller overrode the colour, the pill background should tint to
    # match so the badge reads as cohesive — lean on a faint tint rather than
    # recomputing a full ramp.
    if _normalise_color(color):
        bg = "#ffffff"
        ring = "#e5e7eb"

    name_raw = label if label is not None else metric_name
    name = _truncate(name_raw, _NAME_MAX_CHARS[size_key])
    # Trust score suffix — only on medium/large, not small (compact READMEs).
    score_text = ""
    if trust_score is not None and size_key != "small":
        score_text = f" · {int(round(trust_score * 100))}"

    # The for-the-badge style is a different layout entirely; short-circuit.
    if style_key == "for-the-badge":
        return _render_for_the_badge(
            left="litmus",
            right=status_label,
            accent=accent,
            size_key=size_key,
            metric_name=name_raw,
            metric_url=metric_url,
            status_label=status_label,
        )

    name_esc = escape(name)
    label_esc = escape(status_label + score_text)
    url_esc = escape(metric_url or "", quote=False)

    height = variant["height"]
    radius = variant["radius"]
    dot_r = variant["dot_r"]
    pad_x = variant["pad_x"]
    name_f = variant["name_f"]
    label_f = variant["label_f"]
    brand_f = variant["brand_f"]
    char_w = variant["char_w"]
    min_width = variant["min_width"]

    # Width estimate: dot + name + gap + label + brand wordmark + padding.
    brand_text = "⚗ litmus" if size_key == "large" else "litmus"
    brand_budget = int(len(brand_text) * (char_w * 0.8)) + 16
    width = max(
        min_width,
        pad_x * 2 + dot_r * 2 + 6 + int(len(name) * char_w) + 10
        + int(len(label_esc) * (char_w * 0.95)) + brand_budget,
    )

    sans = (
        'ui-sans-serif, system-ui, -apple-system, '
        '"Segoe UI", Roboto, sans-serif'
    )
    mono = "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace"

    # Geometry inside the outer pill.
    inner_x = pad_x - 4
    inner_w = width - 2 * inner_x
    inner_y = (height - (height - 8)) / 2
    inner_h = height - 8
    inner_radius = max(2, radius - 2)
    dot_cx = pad_x + dot_r
    text_y = height / 2 + name_f / 3
    name_x = dot_cx + dot_r + 6
    label_x = name_x + int(len(name) * char_w) + 8
    brand_x = width - pad_x

    header = (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="litmus trust badge for {name_esc}: {label_esc}">'
    )
    body = f"""{header}
  <title>Powered by Litmus — click for full metric detail</title>
  <desc>{name_esc} — {label_esc}. {url_esc}</desc>
  <style>
    .name {{ font: 600 {name_f}px/1 {sans}; fill: #111827; }}
    .label {{ font: 500 {label_f}px/1 {sans}; fill: {accent}; }}
    .brand {{ font: 500 {brand_f}px/1 {mono}; fill: #6b7280; }}
  </style>
  <rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" \
rx="{radius}" ry="{radius}" fill="#ffffff" stroke="#e5e7eb"/>
  <rect x="{inner_x}" y="{inner_y}" width="{inner_w}" height="{inner_h}" \
rx="{inner_radius}" ry="{inner_radius}" fill="{bg}" stroke="{ring}"/>
  <circle cx="{dot_cx}" cy="{height / 2:.1f}" r="{dot_r}" fill="{accent}"/>
  <text x="{name_x}" y="{text_y:.1f}" class="name">{name_esc}</text>
  <text x="{label_x}" y="{text_y:.1f}" class="label">{label_esc}</text>
  <text x="{brand_x}" y="{text_y:.1f}" text-anchor="end" class="brand">{brand_text}</text>
</svg>"""
    return _wrap_anchor(body, metric_url)
