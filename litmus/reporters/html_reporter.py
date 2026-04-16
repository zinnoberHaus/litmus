"""HTML output reporter using Jinja2 templates."""

from __future__ import annotations

from datetime import datetime, timezone

from jinja2 import Template

from litmus.checks.runner import CheckStatus, CheckSuite
from litmus.spec.metric_spec import MetricSpec

_HTML_TEMPLATE = Template("""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Litmus Trust Report</title>
<style>
  :root { --green: #22c55e; --yellow: #eab308; --red: #ef4444; --gray: #6b7280; }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         background: #f9fafb; color: #1f2937; padding: 2rem; max-width: 900px; margin: 0 auto; }
  h1 { font-size: 1.5rem; margin-bottom: 0.25rem; }
  .subtitle { color: var(--gray); margin-bottom: 2rem; font-size: 0.875rem; }
  .metric { background: white; border-radius: 8px; padding: 1.5rem; margin-bottom: 1rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
  .metric-header { display: flex; justify-content: space-between;
                   align-items: center; margin-bottom: 1rem; }
  .metric-name { font-size: 1.125rem; font-weight: 600; }
  .metric-score { font-size: 0.875rem; font-weight: 600;
                  padding: 0.25rem 0.75rem; border-radius: 9999px; }
  .score-green { background: #dcfce7; color: #166534; }
  .score-yellow { background: #fef9c3; color: #854d0e; }
  .score-red { background: #fee2e2; color: #991b1b; }
  .metric-desc { color: var(--gray); font-size: 0.875rem; margin-bottom: 0.5rem; }
  .metric-meta { color: var(--gray); font-size: 0.75rem; margin-bottom: 1rem; }
  .checks { width: 100%; border-collapse: collapse; }
  .checks td { padding: 0.5rem 0; font-size: 0.875rem; border-bottom: 1px solid #f3f4f6; }
  .checks td:first-child { width: 1.5rem; }
  .checks td:nth-child(2) { font-weight: 500; }
  .status-passed { color: var(--green); }
  .status-warning { color: var(--yellow); }
  .status-failed { color: var(--red); }
  .status-error { color: var(--red); }
  .summary { background: white; border-radius: 8px; padding: 1.5rem; margin-top: 2rem;
             box-shadow: 0 1px 3px rgba(0,0,0,0.1); text-align: center; }
  .summary-stats { display: flex; justify-content: center; gap: 2rem; margin-top: 0.75rem; }
  .stat { text-align: center; }
  .stat-value { font-size: 1.5rem; font-weight: 700; }
  .stat-label { font-size: 0.75rem; color: var(--gray); }
</style>
</head>
<body>
<h1>Litmus Trust Report</h1>
<p class="subtitle">Generated {{ generated_at }}</p>

{% for m in metrics %}
<div class="metric">
  <div class="metric-header">
    <span class="metric-name">{{ m.name }}</span>
    <span class="metric-score {{ m.score_class }}">{{ m.score_display }}</span>
  </div>
  {% if m.description %}<p class="metric-desc">{{ m.description }}</p>{% endif %}
  <p class="metric-meta">
    {% if m.owner %}Owner: {{ m.owner }}{% endif %}
    {% if m.tags %} &middot; Tags: {{ m.tags | join(', ') }}{% endif %}
  </p>
  <table class="checks">
  {% for c in m.checks %}
    <tr>
      <td class="status-{{ c.status }}">{{ c.icon }}</td>
      <td>{{ c.name }}</td>
      <td>{{ c.message }}</td>
    </tr>
  {% endfor %}
  </table>
</div>
{% endfor %}

<div class="summary">
  <strong>{{ summary.total }} metric{{ 's' if summary.total != 1 }} checked</strong>
  <div class="summary-stats">
    <div class="stat"><div class="stat-value" style="color:var(--green)">\
{{ summary.healthy }}</div><div class="stat-label">Healthy</div></div>
    <div class="stat"><div class="stat-value" style="color:var(--yellow)">\
{{ summary.warning }}</div><div class="stat-label">Warning</div></div>
    <div class="stat"><div class="stat-value" style="color:var(--red)">\
{{ summary.failing }}</div><div class="stat-label">Failing</div></div>
  </div>
</div>
</body>
</html>
""")

_STATUS_ICONS = {
    CheckStatus.PASSED: "\u2705",
    CheckStatus.WARNING: "\u26a0\ufe0f",
    CheckStatus.FAILED: "\u274c",
    CheckStatus.ERROR: "\u2757",
}


def generate_html_report(
    specs_and_suites: list[tuple[MetricSpec, CheckSuite]],
) -> str:
    """Generate a self-contained HTML report."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    metrics = []
    for spec, suite in specs_and_suites:
        score, total = suite.trust_score
        if suite.failed > 0 or suite.errors > 0:
            score_class = "score-red"
        elif suite.warnings > 0:
            score_class = "score-yellow"
        else:
            score_class = "score-green"

        checks = []
        for r in suite.results:
            checks.append({
                "name": r.name,
                "status": r.status.value,
                "icon": _STATUS_ICONS[r.status],
                "message": r.message,
            })

        metrics.append({
            "name": spec.name,
            "description": spec.description,
            "owner": spec.owner,
            "tags": spec.tags,
            "score_display": f"{score:g}/{total}",
            "score_class": score_class,
            "checks": checks,
        })

    summary = {
        "total": len(metrics),
        "healthy": sum(
            1 for _, s in specs_and_suites
            if s.failed == 0 and s.errors == 0 and s.warnings == 0
        ),
        "warning": sum(
            1 for _, s in specs_and_suites
            if s.warnings > 0 and s.failed == 0
        ),
        "failing": sum(
            1 for _, s in specs_and_suites
            if s.failed > 0 or s.errors > 0
        ),
    }

    return _HTML_TEMPLATE.render(
        generated_at=now,
        metrics=metrics,
        summary=summary,
    )
