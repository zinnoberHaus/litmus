"""AI-powered run explanations.

The engine takes a failed or errored :class:`~litmus_api.models.Run`, assembles
a prompt from the metric's trust spec, the run's :class:`CheckResult` rows, and
the last five historical runs, then asks Claude for a structured hypothesis +
suggested action. Output is stored in a :class:`RunExplanation` row so repeat
reads are free — re-running the worker upserts the existing row.

Why forced tool-use instead of ``messages.parse()``
===================================================

We want a hard contract on the output shape (``hypothesis``, ``suggested_action``)
without adding Pydantic models that mirror the SQLAlchemy schema. A single
forced-tool call with a JSON schema gives us exactly that — the SDK guarantees
the tool's ``input`` dict has the keys our schema declares, so we can write
straight to the DB without regex-parsing a free-form response.

Privacy
=======

The prompt includes the metric name, description, trust rules, current check
results (including ``actual_value`` / ``threshold_value``), and aggregate
summaries of the last five runs. **No warehouse row data ever leaves the
server.** See ``docs/ai-explanations.md`` for the full disclosure.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy.orm import Session

from litmus_api.models import CheckResult, Metric, Run, RunExplanation

if TYPE_CHECKING:  # pragma: no cover - typing-only
    pass

logger = logging.getLogger(__name__)

# Using Sonnet 4.6 — cheaper and fast enough for an interactive 30s HTTP call.
# Opus is overkill for summarizing a handful of check results; if users want
# deeper analysis later we can expose a model override.
DEFAULT_MODEL_ID = "claude-sonnet-4-6"

_MAX_TOKENS = 800
_HISTORY_LIMIT = 5
_RUN_EXPLAIN_TOOL = "return_run_explanation"

_SYSTEM_PROMPT = (
    "You are Litmus, a data-trust explainer. A user runs automated checks "
    "against their data warehouse; when a check fails, your job is to give "
    "them one short paragraph naming the most likely root cause and one "
    "short, imperative next step they can take right now.\n\n"
    "Rules:\n"
    "- Write in plain English aimed at an analytics engineer or business "
    "metric owner. No jargon, no marketing tone.\n"
    "- Ground every claim in the numbers you are given. If the freshness "
    "check is 14 hours stale, say \"14 hours stale\", not \"quite stale\".\n"
    "- Use the recent-run history to distinguish a one-off spike from a "
    "flapping metric or a multi-day outage — call that out explicitly if "
    "you see the pattern.\n"
    "- Do not invent systems, table names, or SLAs that are not in the "
    "prompt. If you don't know, say what the user should check.\n"
    "- Never exceed 3 sentences for the hypothesis or 2 sentences for the "
    "suggested action."
)

_TOOL_SCHEMA: dict[str, Any] = {
    "name": _RUN_EXPLAIN_TOOL,
    "description": (
        "Return the final run explanation. You must call this tool exactly "
        "once with the hypothesis and the suggested action."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "hypothesis": {
                "type": "string",
                "description": (
                    "2-3 sentences naming the most likely root cause of the "
                    "failure, grounded in the numbers from the prompt."
                ),
            },
            "suggested_action": {
                "type": "string",
                "description": (
                    "1-2 imperative sentences telling the user what to do "
                    "next. Start with a verb."
                ),
            },
        },
        "required": ["hypothesis", "suggested_action"],
    },
}


@dataclass(frozen=True)
class ExplanationPayload:
    """Plain-object view of a :class:`RunExplanation` — useful for tests
    that want to assert on the engine output without touching the ORM row.
    """

    hypothesis: str
    suggested_action: str
    model_id: str


class ExplainError(RuntimeError):
    """Raised when the engine cannot produce an explanation.

    Distinct from :class:`ValueError` (bad input — run not failed/errored) and
    :class:`RuntimeError` for missing config; ``ExplainError`` signals an
    upstream issue we should surface as a 502 to the caller.
    """


def explain_run(
    session: Session,
    run_id: UUID | str,
    *,
    regenerate: bool = False,
    model_id: str | None = None,
    anthropic_client: Any = None,
) -> RunExplanation:
    """Produce (and persist) an AI-generated explanation for a run.

    Parameters
    ----------
    session:
        Active SQLAlchemy session — the caller owns commit/rollback.
    run_id:
        ``runs.id`` to explain.
    regenerate:
        If ``True``, overwrite any existing row; if ``False`` (default),
        return the existing row without hitting the API.
    model_id:
        Override the default model. Defaults to :data:`DEFAULT_MODEL_ID`.
    anthropic_client:
        Optional pre-built ``anthropic.Anthropic`` instance, used by the
        test suite to inject a stub. Production callers should leave this
        ``None`` so we read the API key from the environment.

    Returns
    -------
    RunExplanation
        The persisted row, flushed so ``run.id`` is available.

    Raises
    ------
    ValueError
        If the run does not exist or its status is ``passed`` / ``warning``.
    RuntimeError
        If ``LITMUS_ANTHROPIC_API_KEY`` / ``ANTHROPIC_API_KEY`` is not set
        and no ``anthropic_client`` was provided.
    ExplainError
        If the model returns a malformed response.
    """
    run_id_str = str(run_id)
    run = session.query(Run).filter_by(id=run_id_str).one_or_none()
    if run is None:
        raise ValueError(f"Run {run_id_str} not found")

    status = (run.status or "").lower()
    if status not in {"failed", "error", "errored"}:
        raise ValueError(
            f"Nothing to explain: run {run_id_str} has status {run.status!r}."
            " AI explanations only run on failed or errored runs."
        )

    existing = (
        session.query(RunExplanation).filter_by(run_id=run_id_str).one_or_none()
    )
    if existing is not None and not regenerate:
        return existing

    metric = session.query(Metric).filter_by(id=run.metric_id).one()
    current_results = (
        session.query(CheckResult).filter_by(run_id=run_id_str).all()
    )
    history = _recent_history(session, metric_id=run.metric_id, exclude_run=run_id_str)

    chosen_model = model_id or DEFAULT_MODEL_ID
    client = anthropic_client or _build_client()

    payload = _invoke_model(
        client=client,
        model_id=chosen_model,
        metric=metric,
        run=run,
        current_results=current_results,
        history=history,
    )

    if existing is None:
        row = RunExplanation(
            run_id=run_id_str,
            hypothesis=payload.hypothesis,
            suggested_action=payload.suggested_action,
            model_id=payload.model_id,
        )
        session.add(row)
    else:
        existing.hypothesis = payload.hypothesis
        existing.suggested_action = payload.suggested_action
        existing.model_id = payload.model_id
        row = existing

    session.flush()
    return row


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _build_client() -> Any:
    api_key = os.environ.get("LITMUS_ANTHROPIC_API_KEY") or os.environ.get(
        "ANTHROPIC_API_KEY"
    )
    if not api_key:
        raise RuntimeError(
            "LITMUS_ANTHROPIC_API_KEY not set — the AI run-explanation feature "
            "requires an Anthropic API key. Set LITMUS_ANTHROPIC_API_KEY (or "
            "ANTHROPIC_API_KEY) in the server environment to enable it."
        )
    try:
        import anthropic  # noqa: PLC0415 — optional dep, imported lazily
    except ImportError as exc:  # pragma: no cover - import guard
        raise RuntimeError(
            "The anthropic SDK is not installed. Install litmus-data[ai] to "
            "enable AI-powered run explanations."
        ) from exc
    return anthropic.Anthropic(api_key=api_key)


def _recent_history(
    session: Session,
    *,
    metric_id: str,
    exclude_run: str,
    limit: int = _HISTORY_LIMIT,
) -> list[Run]:
    q = (
        session.query(Run)
        .filter(Run.metric_id == metric_id)
        .filter(Run.id != exclude_run)
        .order_by(Run.started_at.desc())
        .limit(limit)
    )
    return list(q)


def _invoke_model(
    *,
    client: Any,
    model_id: str,
    metric: Metric,
    run: Run,
    current_results: list[CheckResult],
    history: list[Run],
) -> ExplanationPayload:
    user_prompt = _render_prompt(metric, run, current_results, history)

    try:
        response = client.messages.create(
            model=model_id,
            max_tokens=_MAX_TOKENS,
            system=_SYSTEM_PROMPT,
            tools=[_TOOL_SCHEMA],
            tool_choice={"type": "tool", "name": _RUN_EXPLAIN_TOOL},
            messages=[{"role": "user", "content": user_prompt}],
        )
    except Exception as exc:  # noqa: BLE001 — surface any SDK error as ExplainError
        raise ExplainError(f"Anthropic API call failed: {exc}") from exc

    tool_inputs = [
        block.input
        for block in response.content
        if getattr(block, "type", None) == "tool_use"
        and getattr(block, "name", None) == _RUN_EXPLAIN_TOOL
    ]
    if not tool_inputs:
        raise ExplainError(
            "Model did not return a structured explanation "
            f"(stop_reason={getattr(response, 'stop_reason', '?')})"
        )

    data = tool_inputs[0] or {}
    hypothesis = (data.get("hypothesis") or "").strip()
    suggested = (data.get("suggested_action") or "").strip()
    if not hypothesis or not suggested:
        raise ExplainError(
            "Model returned an empty hypothesis or suggested action"
        )

    return ExplanationPayload(
        hypothesis=hypothesis,
        suggested_action=suggested,
        model_id=model_id,
    )


def _render_prompt(
    metric: Metric,
    run: Run,
    current_results: list[CheckResult],
    history: list[Run],
) -> str:
    spec = metric.spec_json or {}
    trust = spec.get("trust") or {}
    trust_rules = json.dumps(trust, indent=2, sort_keys=True, default=str)

    lines: list[str] = []
    lines.append(f"Metric: {metric.name} ({metric.slug})")
    if metric.description:
        lines.append(f"Description: {metric.description}")
    if metric.primary_table:
        lines.append(f"Primary table: {metric.primary_table}")
    lines.append("")
    lines.append("Trust rules (from the .metric file):")
    lines.append(trust_rules)
    lines.append("")
    lines.append(f"Current run: id={run.id}, status={run.status}")
    if run.started_at:
        lines.append(f"Started at: {run.started_at.isoformat()}")
    if run.trust_score is not None:
        lines.append(f"Trust score: {float(run.trust_score):.3f}")
    if run.value_sum is not None:
        lines.append(f"value_sum: {float(run.value_sum)}")
    if run.row_count is not None:
        lines.append(f"row_count: {run.row_count}")
    lines.append("")
    lines.append("Check results from the failing run:")
    if not current_results:
        lines.append("  (no check results recorded — this itself is suspicious)")
    else:
        for r in current_results:
            lines.append(f"  - [{r.status}] {r.rule_type}: {r.message or '(no message)'}")
            if r.actual_value is not None or r.threshold_value is not None:
                av = "?" if r.actual_value is None else float(r.actual_value)
                tv = "?" if r.threshold_value is None else float(r.threshold_value)
                lines.append(f"      actual={av}, threshold={tv}")
    lines.append("")
    lines.append(
        f"Recent run history (up to {_HISTORY_LIMIT} most recent prior runs, "
        "newest first):"
    )
    if not history:
        lines.append("  (no prior runs — this may be the first ever run of this metric)")
    else:
        for h in history:
            ts = h.started_at.isoformat() if h.started_at else "?"
            score = (
                f"{float(h.trust_score):.3f}" if h.trust_score is not None else "—"
            )
            vs = (
                f"{float(h.value_sum)}" if h.value_sum is not None else "—"
            )
            rc = str(h.row_count) if h.row_count is not None else "—"
            lines.append(
                f"  - {ts}  status={h.status}  score={score}  value_sum={vs}  rows={rc}"
            )
    lines.append("")
    lines.append(
        "Call the return_run_explanation tool with a short hypothesis (2-3 "
        "sentences) and a short suggested_action (1-2 imperative sentences)."
    )
    return "\n".join(lines)
