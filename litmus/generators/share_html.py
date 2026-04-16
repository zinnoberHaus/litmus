"""Generate a single-file HTML artefact from a ``MetricSpec``.

Unlike :mod:`litmus.reporters.html_reporter` (which renders the *output* of a
check run for engineers), this module produces the **shareable** view of the
metric definition itself — the thing a finance/ops/product person actually
wants to read. All CSS is inlined, the logo is base64-embedded, and the file
renders fully offline so it can be pasted into Slack, email, or Notion.

The module is intentionally stateless: give it a ``MetricSpec`` and optionally
the latest ``CheckSuite``, and it hands back a complete HTML string.
"""

from __future__ import annotations

import html
import os
from base64 import b64encode
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib.resources import files

from litmus.checks.runner import CheckStatus, CheckSuite
from litmus.spec.metric_spec import MetricSpec

# The Litmus brand mark, embedded at module load so the generated HTML is
# self-contained and renders offline (Slack/email/Notion paste).
_LOGO_BYTES = (files("litmus.generators") / "assets" / "logo-128.png").read_bytes()
_LOGO_PNG_DATA_URI = "data:image/png;base64," + b64encode(_LOGO_BYTES).decode("ascii")


# ───────────────────── rule → human label ──────────────────────


def _rule_labels(spec: MetricSpec) -> list[str]:
    """Human-friendly labels for each Trust rule, in declaration order.

    The order matches what ``run_checks`` produces so we can zip labels with
    CheckResults one-for-one when a suite is supplied.
    """
    trust = spec.trust
    if trust is None:
        return []
    out: list[str] = []
    if trust.freshness:
        out.append(f"Data is no more than {trust.freshness.max_hours:g} hours old")
    for n in trust.null_rules:
        if n.max_percentage == 0:
            out.append(f"No {n.column} values are missing")
        else:
            out.append(
                f"Less than {n.max_percentage:g}% of {n.column} values are missing"
            )
    for v in trust.volume_rules:
        scope = f" in {v.table}" if v.table else ""
        out.append(
            f"Row count{scope} hasn't dropped more than "
            f"{v.max_drop_percentage:g}% {v.period} over {v.period}"
        )
    for r in trust.range_rules:
        out.append(f"Value stays between {r.min_value:,.0f} and {r.max_value:,.0f}")
    for c in trust.change_rules:
        out.append(
            f"Value hasn't changed more than {c.max_change_percentage:g}% "
            f"{c.period} over {c.period}"
        )
    for d in trust.duplicate_rules:
        if d.max_percentage == 0:
            out.append(f"No {d.column} values are duplicated")
        else:
            out.append(
                f"Less than {d.max_percentage:g}% of {d.column} values are duplicated"
            )
    if trust.schema_drift is not None:
        out.append("Column list hasn't changed since the last run")
    for ds in trust.distribution_shift_rules:
        out.append(
            f"Average {ds.column} hasn't shifted more than "
            f"{ds.max_change_percentage:g}% {ds.period} over {ds.period}"
        )
    return out


# ──────────────────── status → pill classes ────────────────────


_STATUS_META: dict[CheckStatus, tuple[str, str, str]] = {
    # (css_class, icon, label)
    CheckStatus.PASSED: ("ok", "\u2713", "Passing"),
    CheckStatus.WARNING: ("warn", "!", "Warning"),
    CheckStatus.FAILED: ("fail", "\u2717", "Failing"),
    CheckStatus.ERROR: ("fail", "?", "Error"),
}


def _status_pill(status: CheckStatus | None) -> tuple[str, str, str]:
    if status is None:
        return ("pending", "\u00b7", "Not yet checked")
    return _STATUS_META[status]


@dataclass
class _RuleRow:
    label: str
    pill_class: str
    icon: str
    status_label: str
    message: str


def _rows(spec: MetricSpec, suite: CheckSuite | None) -> list[_RuleRow]:
    labels = _rule_labels(spec)
    rows: list[_RuleRow] = []

    if suite is None:
        for lbl in labels:
            pc, icon, sl = _status_pill(None)
            rows.append(_RuleRow(lbl, pc, icon, sl, "Run `litmus check` to verify."))
        return rows

    results = suite.results
    if len(results) != len(labels):
        # Order mismatch — render labels without status rather than silently lying.
        for lbl in labels:
            pc, icon, sl = _status_pill(None)
            rows.append(
                _RuleRow(lbl, pc, icon, sl, "Latest run did not include this rule.")
            )
        return rows

    for lbl, res in zip(labels, results):
        pc, icon, sl = _status_pill(res.status)
        rows.append(_RuleRow(lbl, pc, icon, sl, res.message))
    return rows


# ─────────────────────── top-level score ───────────────────────


def _summary(suite: CheckSuite | None) -> tuple[str, str, str]:
    """Return (pill_class, icon, label) for the overall metric health."""
    if suite is None or not suite.results:
        return ("pending", "\u00b7", "Not yet checked")
    if suite.failed or suite.errors:
        return ("fail", "\u2717", "Failing")
    if suite.warnings:
        return ("warn", "!", "Warnings")
    return ("ok", "\u2713", "Healthy")


# ─────────────────────── HTML building ─────────────────────────


def _esc(text: str | None) -> str:
    return html.escape(text, quote=True) if text else ""


def _footer_bits(suite: CheckSuite | None) -> tuple[str, str | None]:
    """Return (last_run_iso_or_empty, commit_sha_or_None).

    Reads GITHUB_SHA / LITMUS_COMMIT_SHA from the environment so the footer is
    deterministic in CI.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    commit = os.environ.get("GITHUB_SHA") or os.environ.get("LITMUS_COMMIT_SHA")
    if commit:
        commit = commit[:7]
    return now, commit


_CSS = """
:root {
  --bg: #f9fafb; --card: #ffffff; --text: #111827; --muted: #6b7280;
  --line: #e5e7eb; --accent: #7c3aed;
  --ok: #16a34a; --okbg: #dcfce7;
  --warn: #ca8a04; --warnbg: #fef9c3;
  --fail: #dc2626; --failbg: #fee2e2;
  --pending: #4b5563; --pendingbg: #f3f4f6;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { background: var(--bg); color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
               Helvetica, Arial, sans-serif;
  line-height: 1.5; }
.page { max-width: 760px; margin: 0 auto; padding: 2.5rem 1.5rem 4rem; }
header.title { display: flex; align-items: center; gap: 0.75rem;
  margin-bottom: 0.5rem; }
header.title img { width: 32px; height: 32px; border-radius: 6px; }
header.title .brand { color: var(--muted); font-size: 0.8rem;
  letter-spacing: 0.05em; text-transform: uppercase; }
h1 { font-size: 1.875rem; font-weight: 700; letter-spacing: -0.01em;
  margin-bottom: 0.25rem; }
.summary-pill { display: inline-flex; align-items: center; gap: 0.4rem;
  padding: 0.35rem 0.75rem; border-radius: 999px; font-weight: 600;
  font-size: 0.875rem; margin-top: 0.25rem; }
.pill-ok       { background: var(--okbg);      color: var(--ok); }
.pill-warn     { background: var(--warnbg);    color: var(--warn); }
.pill-fail     { background: var(--failbg);    color: var(--fail); }
.pill-pending  { background: var(--pendingbg); color: var(--pending); }
.meta { color: var(--muted); font-size: 0.875rem; margin-top: 0.75rem; }
.meta span + span::before { content: " · "; margin: 0 0.35rem;
  color: var(--line); }
section.card { background: var(--card); border: 1px solid var(--line);
  border-radius: 12px; padding: 1.5rem; margin-top: 1.25rem; }
section.card h2 { font-size: 1rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.05em; color: var(--muted); margin-bottom: 0.75rem; }
.description { font-size: 1.05rem; color: var(--text); }
.gwt { display: grid; gap: 0.85rem; }
.gwt .label { display: inline-block; font-weight: 700; text-transform: uppercase;
  font-size: 0.7rem; letter-spacing: 0.08em; color: var(--accent);
  background: #ede9fe; padding: 0.15rem 0.5rem; border-radius: 4px;
  margin-right: 0.5rem; }
.gwt ul { list-style: none; padding-left: 1.25rem; margin-top: 0.5rem; }
.gwt ul li { position: relative; padding: 0.25rem 0; color: var(--text); }
.gwt ul li::before { content: "•"; color: var(--accent); position: absolute;
  left: -1rem; font-weight: 700; }
.trust-list { list-style: none; }
.trust-list li { display: flex; align-items: flex-start; gap: 0.75rem;
  padding: 0.65rem 0; border-bottom: 1px solid var(--line); }
.trust-list li:last-child { border-bottom: none; }
.trust-list .tick { flex-shrink: 0; width: 1.5rem; height: 1.5rem;
  border-radius: 999px; display: inline-flex; align-items: center;
  justify-content: center; font-weight: 700; font-size: 0.85rem; }
.tick-ok       { background: var(--okbg);      color: var(--ok); }
.tick-warn     { background: var(--warnbg);    color: var(--warn); }
.tick-fail     { background: var(--failbg);    color: var(--fail); }
.tick-pending  { background: var(--pendingbg); color: var(--pending); }
.trust-list .body { flex: 1; }
.trust-list .rule { font-weight: 500; }
.trust-list .msg { color: var(--muted); font-size: 0.875rem; margin-top: 0.15rem; }
.empty { color: var(--muted); font-style: italic; }
footer.footer { color: var(--muted); font-size: 0.78rem;
  margin-top: 2.5rem; border-top: 1px solid var(--line); padding-top: 1rem;
  display: flex; justify-content: space-between; flex-wrap: wrap; gap: 0.5rem; }
footer.footer a { color: var(--accent); text-decoration: none; }
"""


def generate_share_html(spec: MetricSpec, suite: CheckSuite | None = None) -> str:
    """Build the single-file HTML artefact."""
    last_run, commit_sha = _footer_bits(suite)
    summary_class, summary_icon, summary_label = _summary(suite)

    # Split conditions into include/exclude for a friendlier Given block.
    includes: list[str] = []
    excludes: list[str] = []
    for c in spec.conditions:
        low = c.lower()
        if any(tok in low for tok in (" not ", "exclude", "without", "n't ")):
            excludes.append(c)
        else:
            includes.append(c)

    rows = _rows(spec, suite)

    parts: list[str] = []
    parts.append("<!DOCTYPE html>")
    parts.append('<html lang="en">')
    parts.append("<head>")
    parts.append('<meta charset="utf-8">')
    parts.append(
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
    )
    parts.append(f"<title>{_esc(spec.name)} · Litmus</title>")
    parts.append(f'<style>{_CSS}</style>')
    parts.append("</head>")
    parts.append('<body><main class="page">')

    # Header
    parts.append('<header class="title">')
    parts.append(f'<img alt="Litmus logo" src="{_LOGO_PNG_DATA_URI}">')
    parts.append('<div><div class="brand">Litmus · Trust report</div></div>')
    parts.append("</header>")
    parts.append(f"<h1>{_esc(spec.name)}</h1>")
    parts.append(
        f'<span class="summary-pill pill-{summary_class}">'
        f"{summary_icon} {summary_label}</span>"
    )
    meta_bits: list[str] = []
    if spec.owner:
        meta_bits.append(f"<span>Owner: {_esc(spec.owner)}</span>")
    if spec.tags:
        meta_bits.append(f"<span>Tags: {_esc(', '.join(spec.tags))}</span>")
    if spec.sources:
        meta_bits.append(f"<span>Source: {_esc(', '.join(spec.sources))}</span>")
    if meta_bits:
        parts.append(f'<p class="meta">{"".join(meta_bits)}</p>')

    # Description
    if spec.description:
        parts.append('<section class="card"><h2>What this is</h2>')
        parts.append(f'<p class="description">{_esc(spec.description)}</p>')
        parts.append("</section>")

    # Given/When/Then
    if includes or excludes or spec.calculations or spec.result_name:
        parts.append('<section class="card"><h2>How it\'s defined</h2>')
        parts.append('<div class="gwt">')
        if includes or excludes:
            parts.append('<div><span class="label">Given</span>')
            parts.append('<ul>')
            for inc in includes:
                parts.append(f'<li>{_esc(inc)}</li>')
            for exc in excludes:
                parts.append(f'<li><em>except:</em> {_esc(exc)}</li>')
            parts.append('</ul></div>')
        if spec.calculations:
            parts.append('<div><span class="label">When we calculate</span>')
            parts.append('<ul>')
            for calc in spec.calculations:
                parts.append(f'<li>{_esc(calc)}</li>')
            parts.append('</ul></div>')
        if spec.result_name:
            parts.append(
                f'<div><span class="label">Then the result is</span>'
                f' <strong>{_esc(spec.result_name)}</strong></div>'
            )
        parts.append('</div></section>')

    # Trust block
    parts.append('<section class="card"><h2>Trust checks</h2>')
    if not rows:
        parts.append(
            '<p class="empty">'
            "No Trust rules defined yet. Add a <code>Trust:</code> block to "
            "make this metric self-verifying."
            "</p>"
        )
    else:
        parts.append('<ul class="trust-list">')
        for row in rows:
            parts.append("<li>")
            parts.append(
                f'<span class="tick tick-{row.pill_class}">{row.icon}</span>'
            )
            parts.append(
                f'<div class="body"><div class="rule">{_esc(row.label)}</div>'
                f'<div class="msg">{_esc(row.status_label)}'
                f" — {_esc(row.message)}</div></div>"
            )
            parts.append("</li>")
        parts.append("</ul>")
    parts.append("</section>")

    # Footer
    footer_bits: list[str] = [f"Last updated {last_run}"]
    if commit_sha:
        footer_bits.append(f"Commit {commit_sha}")
    footer_bits.append(
        'Generated by <a href="https://github.com/anthropics/litmus">Litmus</a>'
    )
    parts.append(
        f'<footer class="footer"><span>{"</span><span>".join(footer_bits)}</span>'
        "</footer>"
    )

    parts.append("</main></body></html>")
    return "\n".join(parts) + "\n"
