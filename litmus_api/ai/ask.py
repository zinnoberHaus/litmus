"""AI-powered natural-language Q&A over the metric catalog.

Engineers ask engine-level questions through ``.metric`` files and CI. PMs ask
"what was revenue last month?" in Slack or the UI and expect a number with a
trust stamp — not SQL, not a YAML file. This module is the bridge.

Architecture (per REFACTOR_BLUEPRINT §2.4, task #54)
====================================================

1. **Intent resolution** — Claude Sonnet 4.6 with a forced
   ``resolve_metric_intent`` tool call. Claude sees the catalog (slug/name/
   description/primary_table/owner) and the user's question; it returns one of
   the tool inputs exactly once. The enum-gated ``time_window`` keeps Claude
   from hallucinating date arithmetic.
2. **SQL templating** — entirely server-side, derived from ``MetricSpec``.
   Claude NEVER generates SQL. This is the privacy + safety bright line.
3. **Execution** — the existing ``BaseConnector`` runs a templated
   ``SELECT SUM(...) FROM <primary_table> WHERE <ts_col> BETWEEN ...`` against
   the configured warehouse. Read-only by convention — ops choose a read-only
   role in ``litmus.yml``.
4. **Trust lookup** — the most recent catalog :class:`Run` supplies the
   ``trust_status`` chip. No run → ``"unknown"``.
5. **Answer formatting** — template-based, no second Claude call. The value is
   already computed; wrapping it in English doesn't need a model.

Privacy
=======

Claude's prompt contains:

- Metric catalog entries: slug, name, description, primary_table, owner
- The user's question verbatim
- The enumerated time-window options

Claude NEVER receives:

- Raw warehouse rows / SQL / the computed value
- API keys or user identity
- Spec text for anything other than the chosen metric's trust rules
- Other orgs' data (single-tenant today)

See ``docs/ai-ask.md`` for the full disclosure.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

from sqlalchemy import desc
from sqlalchemy.orm import Session

from litmus_api.models import Metric, Org, Run

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public contract
# ---------------------------------------------------------------------------

# Mirror explain.py — Sonnet 4.6 is cheap and fast enough for a <30s interactive
# round-trip; PMs don't need Opus-level reasoning for "which metric is this?".
DEFAULT_MODEL_ID = "claude-sonnet-4-6"

# Keep the tool name short — it shows up in logs and error messages.
_ASK_TOOL = "resolve_metric_intent"

TrustStatus = Literal["passed", "warning", "failed", "error", "unknown"]

# The time-window vocabulary is a closed enum so Claude can't invent ranges.
# Extending it is intentional work: add the enum value here + the resolver
# branch in ``_resolve_time_window`` + a test.
TimeWindow = Literal[
    "current_period",
    "last_period",
    "last_7_days",
    "last_30_days",
    "last_quarter",
    "last_year",
    "all_time",
]

_TIME_WINDOWS: tuple[str, ...] = (
    "current_period",
    "last_period",
    "last_7_days",
    "last_30_days",
    "last_quarter",
    "last_year",
    "all_time",
)


@dataclass(frozen=True)
class AskAnswer:
    """Plain-object view of a completed ask. Routes convert this to JSON."""

    answer: str
    metric_slug: str
    metric_name: str | None
    metric_url: str | None
    value: float | None
    trust_status: TrustStatus
    definition_url: str
    explanation: str | None
    run_id: str | None
    time_window: str
    model_id: str
    sql: str | None = None  # Kept for debugging; NEVER sent to Claude.
    filters: list[dict[str, Any]] = field(default_factory=list)


class AskError(RuntimeError):
    """Anything the engine raises that should map to a non-200 HTTP status.

    Route layer inspects ``code`` to pick a status:

    - ``ai_not_configured`` → 500
    - ``metric_not_found`` → 404
    - ``unresolved`` → 422
    - ``warehouse_unavailable`` → 503
    - ``bad_input`` → 400
    """

    def __init__(self, code: str, message: str, *, suggestions: list[str] | None = None):
        super().__init__(message)
        self.code = code
        self.suggestions = suggestions or []


# ---------------------------------------------------------------------------
# Tool schema Claude is forced into
# ---------------------------------------------------------------------------


_SYSTEM_PROMPT = (
    "You are Litmus, a metric-catalog navigator. A user asks a business "
    "question in plain English; your job is to resolve it to exactly one "
    "metric in the provided catalog and a time window.\n\n"
    "Rules:\n"
    "- Pick the metric whose description or name most directly answers the "
    "question. If two look close, prefer the one whose primary_table matches "
    "the question's subject.\n"
    "- Never invent a metric_slug. It must match one of the slugs in the "
    "catalog exactly (case-sensitive).\n"
    "- If you genuinely cannot resolve the question (nothing in the catalog "
    "fits), return confidence < 0.5 and put a one-sentence reason in "
    "unresolved_reason. Do not guess.\n"
    "- time_window is an enum — pick the value closest to the user's phrasing. "
    "Prefer 'last_period' for phrases like 'last month' or 'last quarter' "
    "when the metric is aggregated monthly/quarterly.\n"
    "- filters is reserved for v0.4 group-by; leave it empty unless the "
    "question explicitly names a slice the metric definition supports.\n"
    "- Call resolve_metric_intent exactly once."
)


def _tool_schema() -> dict[str, Any]:
    return {
        "name": _ASK_TOOL,
        "description": (
            "Return the metric + time window that answers the user's "
            "question. Must be called exactly once."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "metric_slug": {
                    "type": "string",
                    "description": (
                        "Slug of the catalog metric. Must match an entry from "
                        "the provided catalog exactly. Empty string if the "
                        "question cannot be resolved."
                    ),
                },
                "time_window": {
                    "type": "string",
                    "enum": list(_TIME_WINDOWS),
                    "description": (
                        "Time range for the metric value. Prefer the most "
                        "specific value that still covers the user's phrasing."
                    ),
                },
                "filters": {
                    "type": "array",
                    "description": (
                        "Reserved for v0.4. Leave empty in v0.3."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "column": {"type": "string"},
                            "op": {"type": "string"},
                            "value": {"type": ["string", "number", "boolean"]},
                        },
                    },
                },
                "confidence": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                    "description": (
                        "0.0–1.0 confidence the chosen metric answers the "
                        "question. <0.5 means 'I'm not sure.'"
                    ),
                },
                "unresolved_reason": {
                    "type": "string",
                    "description": (
                        "One sentence explaining why the question couldn't be "
                        "resolved. Empty string when confidence >= 0.5."
                    ),
                },
            },
            "required": ["metric_slug", "time_window", "confidence"],
        },
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def answer_question(
    session: Session,
    org: Org,
    question: str,
    *,
    metric_slug: str | None = None,
    public_url: str = "",
    connector: Any = None,
    anthropic_client: Any = None,
    model_id: str | None = None,
) -> AskAnswer:
    """Resolve ``question`` to a metric value and a trust status.

    Parameters
    ----------
    session:
        Active SQLAlchemy session — caller owns commit/rollback.
    org:
        The acting org. Scopes the catalog Claude sees.
    question:
        The user's natural-language question, verbatim.
    metric_slug:
        Optional — if provided, skip intent resolution entirely and go
        straight to SQL templating. Lets callers who already know the metric
        (e.g. the in-page ``AskPanel`` on a metric detail page) avoid the
        extra Claude round-trip.
    public_url:
        Base URL for the hosted catalog. Used to build absolute ``metric_url``
        / ``definition_url``. Empty string → relative paths only.
    connector:
        Optional pre-built :class:`BaseConnector`. If ``None`` we build one
        from ``litmus.yml`` via :func:`litmus.config.settings.get_connector`.
        Tests inject a stub to avoid hitting a real warehouse.
    anthropic_client:
        Optional pre-built ``anthropic.Anthropic`` — tests inject a stub.
    model_id:
        Override the default model.

    Raises
    ------
    AskError
        With ``code`` indicating how the route should map the failure.
    """
    if not question or not question.strip():
        raise AskError("bad_input", "question is empty")

    # 1. Intent resolution — unless caller already narrowed it for us.
    if metric_slug:
        metric = _resolve_metric_by_slug(session, org, metric_slug)
        time_window: TimeWindow = "last_period"
        confidence = 1.0
        unresolved_reason = ""
        resolver_notes = "metric_slug provided by caller — intent resolution skipped"
    else:
        intent = _resolve_intent(
            session,
            org,
            question,
            anthropic_client=anthropic_client,
            model_id=model_id,
        )
        if intent["confidence"] < 0.5 or not intent["metric_slug"]:
            raise AskError(
                "unresolved",
                intent.get("unresolved_reason")
                or "I couldn't match this question to a metric in the catalog.",
                suggestions=intent.get("suggestions") or [],
            )
        metric = _resolve_metric_by_slug(session, org, intent["metric_slug"])
        time_window = intent["time_window"]
        confidence = intent["confidence"]
        unresolved_reason = intent.get("unresolved_reason") or ""
        resolver_notes = (
            f"Resolved via Claude (confidence {confidence:.2f})."
            if confidence < 0.85
            else ""
        )

    # 2 + 3. SQL templating + execution.
    value, sql = _compute_value(
        metric=metric, time_window=time_window, connector=connector
    )

    # 4. Trust lookup from the most recent Run.
    latest_run = (
        session.query(Run)
        .filter_by(metric_id=metric.id)
        .order_by(desc(Run.started_at))
        .first()
    )
    trust_status: TrustStatus = _normalize_status(latest_run.status) if latest_run else "unknown"
    run_id = latest_run.id if latest_run else None

    # 5. Answer formatting — template, no second model call.
    answer_text = _format_answer(
        metric=metric,
        value=value,
        trust_status=trust_status,
        time_window=time_window,
    )

    definition_url = _metric_url(public_url, metric.slug)

    explanation_bits: list[str] = []
    if resolver_notes:
        explanation_bits.append(resolver_notes)
    if unresolved_reason:
        explanation_bits.append(unresolved_reason)
    if value is None:
        explanation_bits.append(
            "The warehouse query returned no rows for this time window."
        )
    explanation = " ".join(explanation_bits).strip() or None

    return AskAnswer(
        answer=answer_text,
        metric_slug=metric.slug,
        metric_name=metric.name,
        metric_url=definition_url,
        value=value,
        trust_status=trust_status,
        definition_url=definition_url,
        explanation=explanation,
        run_id=run_id,
        time_window=time_window,
        model_id=model_id or DEFAULT_MODEL_ID,
        sql=sql,
        filters=[],
    )


# ---------------------------------------------------------------------------
# Internals — intent resolution
# ---------------------------------------------------------------------------


def _resolve_intent(
    session: Session,
    org: Org,
    question: str,
    *,
    anthropic_client: Any = None,
    model_id: str | None = None,
) -> dict[str, Any]:
    """Ask Claude which metric + time window answers the question.

    Returns a dict with ``metric_slug`` / ``time_window`` / ``confidence`` /
    ``unresolved_reason`` / ``suggestions``. ``suggestions`` is a list of up
    to 3 other plausible slugs — the route surfaces them to the user on a
    422 ``unresolved`` response.
    """
    catalog = _catalog_for_prompt(session, org)
    if not catalog:
        raise AskError(
            "unresolved",
            "The catalog is empty — there are no metrics to answer from.",
            suggestions=[],
        )

    chosen_model = model_id or DEFAULT_MODEL_ID
    client = anthropic_client or _build_client()

    user_prompt = _render_intent_prompt(question, catalog)
    try:
        response = client.messages.create(
            model=chosen_model,
            max_tokens=400,
            system=_SYSTEM_PROMPT,
            tools=[_tool_schema()],
            tool_choice={"type": "tool", "name": _ASK_TOOL},
            messages=[{"role": "user", "content": user_prompt}],
        )
    except Exception as exc:  # noqa: BLE001 — normalize all SDK errors
        raise AskError("ai_transport", f"Anthropic API call failed: {exc}") from exc

    tool_inputs = [
        block.input
        for block in response.content
        if getattr(block, "type", None) == "tool_use"
        and getattr(block, "name", None) == _ASK_TOOL
    ]
    if not tool_inputs:
        raise AskError(
            "unresolved",
            "The AI did not return a structured intent. Try rephrasing the question.",
        )

    data = tool_inputs[0] or {}
    metric_slug = (data.get("metric_slug") or "").strip()
    time_window = data.get("time_window") or "last_period"
    if time_window not in _TIME_WINDOWS:
        time_window = "last_period"
    confidence = float(data.get("confidence") or 0.0)
    unresolved_reason = (data.get("unresolved_reason") or "").strip()

    # Validate the slug against the catalog we showed Claude — belt-and-
    # braces against the model returning a slug it made up.
    valid_slugs = {entry["slug"] for entry in catalog}
    if metric_slug and metric_slug not in valid_slugs:
        logger.warning(
            "ask: model returned unknown slug %r; treating as unresolved",
            metric_slug,
        )
        metric_slug = ""
        confidence = 0.0
        unresolved_reason = (
            unresolved_reason
            or f"The AI suggested {metric_slug!r} but that metric is not in the catalog."
        )

    # Top-3 suggestions for the UI chips on a 422 unresolved response.
    suggestions = [entry["slug"] for entry in catalog[:3]]

    return {
        "metric_slug": metric_slug,
        "time_window": time_window,
        "confidence": confidence,
        "unresolved_reason": unresolved_reason,
        "suggestions": suggestions,
    }


def _catalog_for_prompt(session: Session, org: Org) -> list[dict[str, Any]]:
    """Trim the catalog to the fields Claude needs — nothing more.

    Excluded on purpose: spec_text, spec_json (full rules), run history,
    warehouse credentials, embed tokens.
    """
    metrics = (
        session.query(Metric)
        .filter_by(org_id=org.id, deleted_at=None)
        .order_by(Metric.name.asc())
        .all()
    )
    return [
        {
            "slug": m.slug,
            "name": m.name,
            "description": m.description or "",
            "primary_table": m.primary_table or "",
            "owner": m.owner_email or "",
        }
        for m in metrics
    ]


def _render_intent_prompt(question: str, catalog: list[dict[str, Any]]) -> str:
    """Build the user-turn prompt.

    Kept as plain text (no XML, no JSON wrapping) — Claude reads it more
    reliably and the prompt stays diff-friendly for review.
    """
    lines: list[str] = ["Catalog of available metrics:", ""]
    for entry in catalog:
        lines.append(f"- slug: {entry['slug']}")
        lines.append(f"  name: {entry['name']}")
        if entry["description"]:
            lines.append(f"  description: {entry['description']}")
        if entry["primary_table"]:
            lines.append(f"  primary_table: {entry['primary_table']}")
        if entry["owner"]:
            lines.append(f"  owner: {entry['owner']}")
    lines.append("")
    lines.append("Time window enum (pick one):")
    for window in _TIME_WINDOWS:
        lines.append(f"  - {window}")
    lines.append("")
    lines.append(f"User question: {question.strip()}")
    lines.append("")
    lines.append(
        "Call resolve_metric_intent with your best match. If nothing fits, "
        "return confidence < 0.5 with a one-sentence unresolved_reason."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internals — SQL templating + execution
# ---------------------------------------------------------------------------


def _resolve_metric_by_slug(session: Session, org: Org, slug: str) -> Metric:
    metric = (
        session.query(Metric)
        .filter_by(org_id=org.id, slug=slug, deleted_at=None)
        .one_or_none()
    )
    if metric is None:
        raise AskError(
            "metric_not_found",
            f"Metric {slug!r} not found in the catalog.",
        )
    return metric


def _compute_value(
    *,
    metric: Metric,
    time_window: str,
    connector: Any,
) -> tuple[float | None, str]:
    """Template a SQL query from the stored spec, run it, return the scalar.

    Claude never sees this SQL. The only inputs are:

    - ``metric.primary_table`` from the catalog (server-verified)
    - ``time_window`` from the enum (server-verified)
    - The timestamp column from the spec (defaults to ``updated_at``)

    Returns ``(value, sql)`` — the SQL is surfaced for logs/debugging but
    deliberately NEVER included in the LLM prompt.
    """
    primary_table = metric.primary_table
    if not primary_table:
        raise AskError(
            "bad_input",
            f"Metric {metric.slug!r} has no primary_table — the spec needs at least one Source.",
        )

    spec = metric.spec_json or {}
    # Default aggregation column is 'amount' — matches the existing runner
    # default. Users can override via spec header metadata in a future iteration.
    value_column = _extract_value_column(spec)
    ts_column = _extract_timestamp_column(spec)

    where_clause = _build_where_clause(ts_column, time_window)
    if where_clause:
        sql = (
            f"SELECT SUM({value_column}) AS metric_value "
            f"FROM {primary_table} "
            f"WHERE {where_clause} "
            f"LIMIT 1"
        )
    else:
        sql = (
            f"SELECT SUM({value_column}) AS metric_value "
            f"FROM {primary_table} "
            f"LIMIT 1"
        )

    # Execute against the warehouse.
    close_after = False
    conn = connector
    if conn is None:
        conn = _build_connector()
        close_after = True

    try:
        rows = conn.execute_query(sql)
    except Exception as exc:  # noqa: BLE001 — normalize to AskError
        raise AskError(
            "warehouse_unavailable",
            f"Warehouse query failed: {exc}",
        ) from exc
    finally:
        if close_after:
            try:
                conn.close()
            except Exception:  # pragma: no cover - best-effort
                pass

    if not rows:
        return None, sql
    row = rows[0]
    raw = row.get("metric_value")
    if raw is None:
        raw = row.get("METRIC_VALUE")  # Snowflake upper-cases
    if raw is None:
        return None, sql
    try:
        return float(raw), sql
    except (TypeError, ValueError):
        return None, sql


def _extract_value_column(spec: dict[str, Any]) -> str:
    """Guess the numeric column to aggregate. Conservative default.

    v0.3 reuses the same ``amount`` default the runner applies for range
    checks. A future spec field (``value_column:`` header) will override this
    without changing ``ask.py``.
    """
    # If any range_rule exists, the default aggregation column is the same one
    # range checks use. Keep this in lockstep with checks/runner.py.
    return "amount"


def _extract_timestamp_column(spec: dict[str, Any]) -> str:
    """Guess the timestamp column for time-window filters. Defaults to
    ``updated_at`` to match the runner's freshness-check default."""
    return "updated_at"


def _build_where_clause(ts_column: str, time_window: str) -> str:
    """Resolve a ``TimeWindow`` enum value to a concrete WHERE fragment.

    Dates are computed server-side using the current UTC time — Claude never
    gets to pick the boundary. Returns an empty string for ``all_time`` so
    the caller skips the ``WHERE`` entirely.
    """
    if time_window == "all_time":
        return ""

    now = datetime.now(timezone.utc)
    today = now.date()

    start: date
    end: date

    if time_window == "current_period":
        # Default to the current calendar month.
        start = date(today.year, today.month, 1)
        end = today + timedelta(days=1)
    elif time_window == "last_period":
        # Default to the previous calendar month.
        if today.month == 1:
            start = date(today.year - 1, 12, 1)
            end = date(today.year, 1, 1)
        else:
            start = date(today.year, today.month - 1, 1)
            end = date(today.year, today.month, 1)
    elif time_window == "last_7_days":
        start = today - timedelta(days=7)
        end = today + timedelta(days=1)
    elif time_window == "last_30_days":
        start = today - timedelta(days=30)
        end = today + timedelta(days=1)
    elif time_window == "last_quarter":
        # 90-day approximation — good enough for a scalar "last quarter"
        # question. Calendar-quarter boundaries are a nice-to-have for v0.4.
        start = today - timedelta(days=90)
        end = today + timedelta(days=1)
    elif time_window == "last_year":
        start = today - timedelta(days=365)
        end = today + timedelta(days=1)
    else:  # pragma: no cover - enum exhaustiveness, defense-in-depth
        return ""

    # Use ISO strings — every warehouse we support parses them.
    return f"{ts_column} >= '{start.isoformat()}' AND {ts_column} < '{end.isoformat()}'"


def _build_connector() -> Any:
    """Lazy-construct a warehouse connector from ``litmus.yml``.

    Ops deployments of the server typically don't ship ``litmus.yml`` right
    next to the FastAPI app — the Python CLI runs from a user machine, the
    server runs from a container. For now we fall back to an in-memory
    DuckDB which returns empty results: the engine still answers with
    ``value=None`` + ``trust_status`` from the catalog Run, which is the
    graceful-degradation shape we want.
    """
    config_path = os.environ.get("LITMUS_CONFIG", "litmus.yml")
    try:
        from litmus.config.settings import get_connector, load_config  # noqa: PLC0415

        config = load_config(config_path)
        connector = get_connector(config)
        connector.connect()
        return connector
    except Exception as exc:  # noqa: BLE001 — any failure → in-memory fallback
        logger.warning(
            "ask: falling back to in-memory DuckDB (%s). "
            "Point LITMUS_CONFIG at your litmus.yml for warehouse-backed answers.",
            exc,
        )
        from litmus.connectors.duckdb import DuckDBConnector  # noqa: PLC0415

        connector = DuckDBConnector(database=":memory:")
        connector.connect()
        return connector


# ---------------------------------------------------------------------------
# Internals — trust + formatting
# ---------------------------------------------------------------------------


def _normalize_status(status: str | None) -> TrustStatus:
    if not status:
        return "unknown"
    s = str(status).strip().lower()
    if s in {"passed", "pass"}:
        return "passed"
    if s in {"warning", "warn"}:
        return "warning"
    if s in {"failed", "fail"}:
        return "failed"
    if s in {"error", "errored"}:
        return "error"
    return "unknown"


def _format_value(value: float | None) -> str:
    """Format a numeric value for an English sentence.

    Heuristic only — we don't know the metric's unit from the spec in v0.3.
    Big integers get thousands separators; sub-1 values get 3 decimals.
    """
    if value is None:
        return "no data"
    if abs(value) >= 1000:
        return f"{value:,.0f}"
    if abs(value) >= 1:
        return f"{value:,.2f}"
    return f"{value:.3f}"


def _window_phrase(time_window: str) -> str:
    return {
        "current_period": "the current period",
        "last_period": "the last period",
        "last_7_days": "the last 7 days",
        "last_30_days": "the last 30 days",
        "last_quarter": "the last quarter",
        "last_year": "the last year",
        "all_time": "all time",
    }.get(time_window, time_window)


_TRUST_CLAUSE: dict[str, str] = {
    "passed": "Trust is green — all checks passed on the latest run.",
    "warning": (
        "One or more checks are in warning on the latest run — "
        "treat this number as provisional."
    ),
    "failed": "Trust is failing on the latest run — confirm before acting on this number.",
    "error": "The latest trust run errored — the number may be stale.",
    "unknown": "No trust run has been recorded yet — the number is unverified.",
}


def _format_answer(
    *,
    metric: Metric,
    value: float | None,
    trust_status: TrustStatus,
    time_window: str,
) -> str:
    name = metric.name
    value_str = _format_value(value)
    window = _window_phrase(time_window)
    trust_clause = _TRUST_CLAUSE.get(trust_status, _TRUST_CLAUSE["unknown"])

    if value is None:
        return (
            f"I couldn't find a value for {name} over {window} in the warehouse. "
            f"{trust_clause}"
        )
    return f"{name} for {window} was {value_str}. {trust_clause}"


def _metric_url(public_url: str, slug: str) -> str:
    base = (public_url or "").rstrip("/")
    path = f"/metrics/{slug}"
    return f"{base}{path}" if base else path


# ---------------------------------------------------------------------------
# Internals — client construction
# ---------------------------------------------------------------------------


def _build_client() -> Any:
    api_key = os.environ.get("LITMUS_ANTHROPIC_API_KEY") or os.environ.get(
        "ANTHROPIC_API_KEY"
    )
    if not api_key:
        raise AskError(
            "ai_not_configured",
            "AI Q&A is not configured. Set LITMUS_ANTHROPIC_API_KEY or install 'litmus-data[ai]'.",
        )
    try:
        import anthropic  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - import guard
        raise AskError(
            "ai_not_configured",
            "The anthropic SDK is not installed. Install litmus-data[ai] to enable AI Q&A.",
        ) from exc
    return anthropic.Anthropic(api_key=api_key)
