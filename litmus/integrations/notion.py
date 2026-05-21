"""Notion integration — payload shapes for ops-pilot to push.

Actual writes happen through the Notion MCP server (the ``ops-pilot``
agent calls ``mcp__plugin_Notion_notion__*`` tools). This module defines
the canonical payload shape so the agent has a contract to render against.
"""

from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProjectSnapshot:
    """Everything ``ops-pilot`` needs to update the Notion playbook page."""

    project_name: str
    warehouse: str
    sources: list[dict[str, Any]] = field(default_factory=list)
    pipelines: list[dict[str, Any]] = field(default_factory=list)
    dashboards: list[dict[str, Any]] = field(default_factory=list)
    trust_scorecard: list[dict[str, Any]] = field(default_factory=list)
    open_issues: int = 0
    recent_activity: list[str] = field(default_factory=list)
    synced_at: dt.datetime = field(default_factory=dt.datetime.utcnow)

    def to_markdown(self) -> str:
        """Render the snapshot as markdown the MCP can convert to Notion blocks."""
        lines = [
            f"# {self.project_name}",
            "",
            f"_Last synced: {self.synced_at:%Y-%m-%d %H:%M} UTC_",
            "",
            "## Data sources",
        ]
        for s in self.sources:
            name = s.get("name", "?")
            kind = s.get("type", "?")
            table = s.get("table", "?")
            lines.append(f"- **{name}** — {kind} → `{table}`")
        if not self.sources:
            lines.append("_(none registered — run `/dp-ingest` to add one)_")

        lines += ["", "## Pipelines"]
        for p in self.pipelines:
            lines.append(f"- `{p.get('name', '?')}` — last run {p.get('last_run', 'never')}")
        if not self.pipelines:
            lines.append("_(none)_")

        lines += ["", "## Dashboards"]
        for d in self.dashboards:
            lines.append(f"- [{d.get('name', '?')}]({d.get('url', '#')})")
        if not self.dashboards:
            lines.append("_(none — run `/dp-dashboard` to scaffold one)_")

        lines += ["", "## Trust scorecard"]
        for t in self.trust_scorecard:
            status = "PASS" if t.get("failed", 0) == 0 else "FAIL"
            metric = t.get("metric", "?")
            score = t.get("score", 0)
            lines.append(f"- `{metric}`: **{status}** (score {score:.0%})")
        if not self.trust_scorecard:
            lines.append("_(no checks recorded yet)_")

        lines += [
            "",
            f"## Open issues: {self.open_issues}",
            "",
            "## Recent activity",
        ]
        for a in self.recent_activity[-10:]:
            lines.append(f"- {a}")

        return "\n".join(lines)


def is_configured() -> bool:
    return bool(os.environ.get("NOTION_API_KEY"))
