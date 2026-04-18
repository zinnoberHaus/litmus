"""SVG generator for the embeddable trust badge — the viral wedge.

Rendered output is a ~150x30 pill with:
  - coloured status dot
  - metric name (ellipsised)
  - status label (Trusted / Review / Broken / Unknown)
  - trust score, if known
  - `litmus` wordmark on the right

Colours are locked to the same palette as ui/components/TrustBadge.tsx so the
Notion/Slack-embedded version matches the in-app card pixel for pixel.
"""

from __future__ import annotations

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


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def render_badge_svg(
    *,
    metric_name: str,
    status: str,
    trust_score: float | None = None,
) -> str:
    key = (status or "unknown").lower()
    dot, bg, ring = _STATUS_COLOURS.get(key, _STATUS_COLOURS["unknown"])
    label = _STATUS_COPY.get(key, status.title() if status else "Unknown")

    name = _truncate(metric_name, 28)
    score_text = ""
    if trust_score is not None:
        score_text = f" · {int(round(trust_score * 100))}"

    name_esc = escape(name)
    label_esc = escape(label + score_text)

    # Estimated width — name font is 13px bold, label is 12px regular.
    # Use a generous per-char budget (7.5px) so most metrics fit on one line.
    approx_width = max(260, 70 + int(len(name) * 7.5) + int(len(label_esc) * 7.2))

    sans = (
        'ui-sans-serif, system-ui, -apple-system, '
        '"Segoe UI", Roboto, sans-serif'
    )
    mono = "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace"
    name_x = 30 + int(len(name) * 7.5) + 6
    outer = approx_width - 1
    inner = approx_width - 60
    header = (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{approx_width}" height="36" '
        f'viewBox="0 0 {approx_width} 36" role="img" '
        f'aria-label="litmus trust badge for {name_esc}: {label_esc}">'
    )
    return f"""{header}
  <title>{name_esc} — {label_esc}</title>
  <style>
    .name {{ font: 600 13px/1 {sans}; fill: #111827; }}
    .label {{ font: 500 12px/1 {sans}; fill: {dot}; }}
    .brand {{ font: 500 10px/1 {mono}; fill: #6b7280; }}
  </style>
  <rect x="0.5" y="0.5" width="{outer}" height="35" rx="8" ry="8"
        fill="#ffffff" stroke="#e5e7eb"/>
  <rect x="4" y="4" width="{inner}" height="28" rx="14" ry="14"
        fill="{bg}" stroke="{ring}"/>
  <circle cx="18" cy="18" r="4" fill="{dot}"/>
  <text x="30" y="22" class="name">{name_esc}</text>
  <text x="{name_x}" y="22" class="label">{label_esc}</text>
  <text x="{approx_width - 8}" y="22" text-anchor="end" class="brand">litmus</text>
</svg>"""
