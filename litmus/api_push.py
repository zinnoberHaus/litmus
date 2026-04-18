"""Push local `litmus check` results to a hosted Litmus server.

Thin wrapper that uses the standard-library ``urllib`` so pushing does not
pull in ``httpx`` / ``requests`` as hard deps for CLI-only users.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from litmus.checks.runner import CheckResult, CheckSuite
    from litmus.spec.metric_spec import MetricSpec


class PushError(RuntimeError):
    """Raised when pushing to the Litmus server fails."""


@dataclass
class PushConfig:
    endpoint: str
    api_key: str | None = None
    commit_sha: str | None = None
    ci_run_id: str | None = None

    @classmethod
    def from_env(
        cls,
        endpoint: str | None = None,
        api_key: str | None = None,
    ) -> PushConfig | None:
        ep = endpoint or os.environ.get("LITMUS_ENDPOINT")
        if not ep:
            return None
        return cls(
            endpoint=ep.rstrip("/"),
            api_key=api_key or os.environ.get("LITMUS_API_KEY"),
            commit_sha=(
                os.environ.get("GITHUB_SHA") or os.environ.get("LITMUS_COMMIT_SHA")
            ),
            ci_run_id=(
                os.environ.get("GITHUB_RUN_ID") or os.environ.get("LITMUS_RUN_ID")
            ),
        )


def _request(cfg: PushConfig, method: str, path: str, payload: dict[str, Any]) -> dict:
    url = f"{cfg.endpoint}{path}"
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if cfg.api_key:
        headers["Authorization"] = f"Bearer {cfg.api_key}"
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise PushError(f"{method} {path} → {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise PushError(f"Could not reach {cfg.endpoint}: {exc.reason}") from exc


def _overall_status(suite: CheckSuite) -> str:
    from litmus.checks.runner import CheckStatus

    statuses = {r.status for r in suite.results}
    if CheckStatus.ERROR in statuses:
        return "error"
    if CheckStatus.FAILED in statuses:
        return "failed"
    if CheckStatus.WARNING in statuses:
        return "warning"
    return "passed"


def _to_check_payload(r: CheckResult) -> dict[str, Any]:
    actual = r.actual_value if isinstance(r.actual_value, (int, float)) else None
    threshold = r.threshold if isinstance(r.threshold, (int, float)) else None
    return {
        "rule_type": r.name,
        "rule": r.details or {},
        "status": r.status.value,
        "message": r.message,
        "actual_value": actual,
        "threshold_value": threshold,
    }


def push_results(
    cfg: PushConfig,
    results: list[tuple[MetricSpec, CheckSuite]],
    *,
    spec_texts: dict[str, str] | None = None,
) -> list[str]:
    """Upsert each metric then POST one run per spec. Returns metric IDs."""
    spec_texts = spec_texts or {}
    metric_ids: list[str] = []
    for spec, suite in results:
        spec_text = spec_texts.get(spec.name) or spec.raw_text
        if not spec_text:
            raise PushError(
                f"Cannot push metric {spec.name}: raw spec text is missing"
            )
        m = _request(
            cfg,
            "POST",
            "/api/v1/metrics",
            {
                "spec_text": spec_text,
                "source_sha": cfg.commit_sha,
                "source_path": None,
            },
        )
        metric_id = m["id"]
        metric_ids.append(metric_id)

        score, total = suite.trust_score
        trust_score = score / total if total else None
        now = datetime.now(timezone.utc).isoformat()
        _request(
            cfg,
            "POST",
            "/api/v1/runs",
            {
                "metric_id": metric_id,
                "status": _overall_status(suite),
                "trust_score": trust_score,
                "started_at": now,
                "finished_at": now,
                "commit_sha": cfg.commit_sha,
                "ci_run_id": cfg.ci_run_id,
                "triggered_by": "cli",
                "check_results": [_to_check_payload(r) for r in suite.results],
            },
        )
    return metric_ids


def read_spec_texts(
    paths: list[Path], specs_by_name: dict[str, MetricSpec]
) -> dict[str, str]:
    """Map metric name → raw .metric file text so upsert sees the original source."""
    out: dict[str, str] = {}
    for p in paths:
        try:
            text = Path(p).read_text(encoding="utf-8")
        except OSError:
            continue
        for name in specs_by_name:
            if name in text:
                out[name] = text
    return out
