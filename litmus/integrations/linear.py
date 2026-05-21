"""Linear integration — issue payload shapes for ops-pilot to push.

Actual writes happen through the Linear MCP server (the ``ops-pilot``
agent calls ``mcp__claude_ai_Linear__*`` tools). This module defines
the canonical issue payload + dedup helpers.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from typing import Literal

IssueKind = Literal["trust-regression", "todo", "reviewer-blocker", "bug"]


@dataclass
class IssueDraft:
    """An issue ops-pilot should ensure exists in Linear."""

    title: str
    body: str
    kind: IssueKind
    labels: list[str] = field(default_factory=list)
    dedup_key: str = ""

    def __post_init__(self) -> None:
        if not self.dedup_key:
            self.dedup_key = hashlib.sha1(
                f"{self.kind}::{self.title}".encode()
            ).hexdigest()[:12]
        if self.kind not in self.labels:
            self.labels.append(self.kind)


def trust_regression_issue(metric: str, rule: str, history: list[dict]) -> IssueDraft:
    """Draft a Linear issue for a trust regression."""
    lines = [
        f"Metric `{metric}` failed rule `{rule}` for 3+ consecutive runs.",
        "",
        "Recent history:",
    ]
    for h in history[-5:]:
        lines.append(f"- {h.get('recorded_at')}: {h.get('status')} ({h.get('message', '')})")
    lines += [
        "",
        "Fix the pipeline or, if the threshold is wrong, tighten the rule "
        f"in `metrics/{metric}.metric`.",
    ]
    return IssueDraft(
        title=f"[trust] {metric} failed: {rule}",
        body="\n".join(lines),
        kind="trust-regression",
        labels=["trust"],
    )


def todo_issue(file: str, line: int, text: str) -> IssueDraft:
    """Draft an issue from a TODO comment found in a transform or metric."""
    return IssueDraft(
        title=f"TODO in {file}:{line}",
        body=f"`{file}:{line}` contains:\n\n> {text}\n\nResolve or remove the TODO.",
        kind="todo",
        labels=["pipeline"],
    )


def is_configured() -> bool:
    return bool(os.environ.get("LINEAR_API_KEY"))
