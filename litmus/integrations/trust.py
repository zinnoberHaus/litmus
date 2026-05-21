"""Adapter that runs Litmus trust checks against mart tables.

Wraps the core ``litmus.checks`` runner with the mart-table convention
the agent team uses (``mart_<name>`` table backed by ``metrics/<name>.metric``).
Other code (pipeline runner, Streamlit dashboards) calls into this module
rather than building the connector + parser dance themselves.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

METRICS_DIR = Path("metrics")


def check_table(table: str, warehouse_url: str | None = None) -> Any:
    """Run the trust check for ``metrics/<table>.metric`` and return the suite.

    Returns None if the .metric file doesn't exist (callers should treat
    'no contract' as 'no opinion').
    """
    metric_file = METRICS_DIR / f"{table}.metric"
    if not metric_file.exists():
        return None

    from litmus.checks.runner import run_checks
    from litmus.config.settings import get_connector, load_config
    from litmus.parser import parse_metric_file

    cfg = load_config(None)
    connector = get_connector(cfg)
    try:
        connector.connect()
        spec = parse_metric_file(str(metric_file))
        return run_checks(connector, spec)
    finally:
        connector.close()


def check_all_metrics(warehouse_url: str | None = None) -> list[tuple[str, Any]]:
    """Run every .metric file and return a list of (table, suite) pairs."""
    if not METRICS_DIR.exists():
        return []

    results = []
    for metric_file in sorted(METRICS_DIR.glob("*.metric")):
        suite = check_table(metric_file.stem, warehouse_url)
        if suite:
            display = getattr(suite, "trust_score_display", None) or "n/a"
            print(f"[trust] {metric_file.stem}: {display}, failed={suite.failed}")
            results.append((metric_file.stem, suite))
    return results
