"""Slack routes — sign-off workflow + slash commands + interactions.

Every inbound endpoint verifies Slack's HMAC signature against
``LITMUS_SLACK_SIGNING_SECRET`` before touching state. Outbound posts go
via :mod:`litmus_api.slack.client` (stdlib ``urllib.request`` — no new
hard deps).

v0.3 scope (per REFACTOR_BLUEPRINT.md §2.3, task #52):

* ``POST /slack/events`` — Events API callback. Handles ``url_verification``
  and returns 200 stubs for ``app_mention`` / ``message.*``. Task #54 fills
  in the AI Q&A logic for ``app_mention``.
* ``POST /slack/commands`` — slash command handler.
* ``POST /slack/interactions`` — button clicks from Block Kit messages.
* ``POST /slack/signoff/request`` — internal endpoint the upsert path calls
  to post a sign-off prompt when a new revision requires one.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlalchemy.orm import Session

from litmus_api.deps import current_org, db_session
from litmus_api.models import Metric, MetricRevision, Org
from litmus_api.slack import client as slack_client
from litmus_api.slack.signatures import is_valid_signature

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/slack", tags=["slack"])

_SIGNING_SECRET_ENV = "LITMUS_SLACK_SIGNING_SECRET"
_WEBHOOK_URL_ENV = "LITMUS_SLACK_WEBHOOK_URL"
_DEFAULT_CHANNEL_ENV = "LITMUS_SLACK_DEFAULT_CHANNEL"


# ── signature guard ───────────────────────────────────────────────────


async def _verify_slack_request(
    request: Request,
    x_slack_signature: str | None,
    x_slack_request_timestamp: str | None,
) -> bytes:
    """Read the raw body and verify Slack's signature against it.

    Returns the raw body (so callers can re-parse without another await on
    ``request.body()``). Raises 401 on any verification failure — fail
    closed, never silently accept. Mirrors the GitHub webhook pattern.
    """
    secret = os.environ.get(_SIGNING_SECRET_ENV)
    if not secret:
        # Operator has not configured the secret. Fail closed so Slack's
        # delivery UI shows a clear "unauthorized" rather than silently
        # accepting spoofed requests.
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            f"{_SIGNING_SECRET_ENV} is not configured on the server",
        )

    body = await request.body()
    if not is_valid_signature(
        secret, x_slack_request_timestamp, body, x_slack_signature
    ):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "invalid Slack signature"
        )
    return body


# ── /slack/events ─────────────────────────────────────────────────────


@router.post("/events")
async def slack_events(
    request: Request,
    x_slack_signature: str | None = Header(default=None),
    x_slack_request_timestamp: str | None = Header(default=None),
) -> dict[str, Any]:
    """Slack Events API callback.

    v0.3 handles two things:

    1. ``url_verification`` — Slack's initial handshake when you register
       the Events URL. Return the ``challenge`` string verbatim.
    2. Everything else — log + 200. Task #54 fills in ``app_mention`` with
       the AI Q&A logic; for now we just ack so Slack doesn't disable the
       subscription after repeated 4xxs.
    """
    body = await _verify_slack_request(
        request, x_slack_signature, x_slack_request_timestamp
    )

    try:
        payload = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"invalid JSON body: {exc}"
        ) from exc

    # URL verification — Slack wants the challenge token echoed back.
    if payload.get("type") == "url_verification":
        challenge = payload.get("challenge")
        if not isinstance(challenge, str):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "missing challenge"
            )
        return {"challenge": challenge}

    # TODO(#54): dispatch ``event_callback`` → ``app_mention`` to the AI
    # Q&A handler. For now we log and ack so Slack keeps the subscription
    # healthy.
    event = payload.get("event") or {}
    logger.info(
        "slack event received: type=%s subtype=%s (stubbed; #54 fills in)",
        event.get("type"),
        event.get("subtype"),
    )
    return {"ok": True}


# ── /slack/commands ───────────────────────────────────────────────────


@router.post("/commands")
async def slack_commands(
    request: Request,
    x_slack_signature: str | None = Header(default=None),
    x_slack_request_timestamp: str | None = Header(default=None),
    org: Org = Depends(current_org),
    session: Session = Depends(db_session),
) -> dict[str, Any]:
    """Slash command handler.

    Slack sends slash commands as ``application/x-www-form-urlencoded``.
    v0.3 supports the ``/litmus-signoff`` command with two subcommands:

    * ``/litmus-signoff pending`` — list pending sign-offs in-channel.
    * ``/litmus-signoff metric <slug>`` — manually request sign-off on
      the latest revision of ``<slug>``.

    Task #54 adds ``/ask <question>`` through the same route.
    """
    body = await _verify_slack_request(
        request, x_slack_signature, x_slack_request_timestamp
    )

    # Slack wraps list values but slash commands are simple scalars — keep
    # the first value per key for ergonomic access.
    form = {k: v[0] if v else "" for k, v in parse_qs(body.decode("utf-8")).items()}
    command = form.get("command", "")
    text = (form.get("text") or "").strip()

    if command == "/litmus-signoff":
        return _handle_signoff_command(session, org, text)

    # Unknown command — respond ephemerally so only the invoker sees it,
    # without triggering a Slack retry.
    return {
        "response_type": "ephemeral",
        "text": f"Unknown command: {command or '(empty)'}",
    }


def _handle_signoff_command(
    session: Session, org: Org, text: str
) -> dict[str, Any]:
    """Dispatch the two ``/litmus-signoff`` subcommands."""
    tokens = text.split()
    if not tokens or tokens[0] == "pending":
        return _list_pending_signoffs(session, org)

    if tokens[0] == "metric" and len(tokens) >= 2:
        return _request_signoff_for_slug(session, org, tokens[1])

    return {
        "response_type": "ephemeral",
        "text": (
            "Usage: `/litmus-signoff pending` or "
            "`/litmus-signoff metric <slug>`"
        ),
    }


def _list_pending_signoffs(session: Session, org: Org) -> dict[str, Any]:
    pending = (
        session.query(MetricRevision, Metric)
        .join(Metric, MetricRevision.metric_id == Metric.id)
        .filter(Metric.org_id == org.id, MetricRevision.signoff_status == "pending")
        .order_by(desc(MetricRevision.created_at))
        .limit(25)
        .all()
    )
    if not pending:
        return {
            "response_type": "ephemeral",
            "text": "No pending sign-offs.",
        }

    lines = [f"*{len(pending)} pending sign-off(s):*"]
    for rev, metric in pending:
        lines.append(
            f"• `{metric.slug}` — revision `{rev.id[:8]}` "
            f"(requested {rev.created_at:%Y-%m-%d %H:%M UTC})"
        )
    return {"response_type": "ephemeral", "text": "\n".join(lines)}


def _request_signoff_for_slug(
    session: Session, org: Org, slug: str
) -> dict[str, Any]:
    metric = (
        session.query(Metric)
        .filter_by(org_id=org.id, slug=slug, deleted_at=None)
        .one_or_none()
    )
    if metric is None:
        return {
            "response_type": "ephemeral",
            "text": f"Metric `{slug}` not found.",
        }

    latest = (
        session.query(MetricRevision)
        .filter_by(metric_id=metric.id)
        .order_by(desc(MetricRevision.created_at))
        .first()
    )
    if latest is None:
        return {
            "response_type": "ephemeral",
            "text": f"Metric `{slug}` has no revisions yet.",
        }

    latest.signoff_required = True
    latest.signoff_status = "pending"
    session.flush()

    _post_signoff_to_slack(session, metric, latest)
    session.commit()
    return {
        "response_type": "in_channel",
        "text": f"Sign-off requested for `{metric.slug}`.",
    }


# ── /slack/interactions ───────────────────────────────────────────────


@router.post("/interactions")
async def slack_interactions(
    request: Request,
    x_slack_signature: str | None = Header(default=None),
    x_slack_request_timestamp: str | None = Header(default=None),
    org: Org = Depends(current_org),
    session: Session = Depends(db_session),
) -> dict[str, Any]:
    """Handle button clicks from Block Kit messages.

    Slack posts interactions as form-encoded with a single ``payload`` field
    containing the JSON body. We resolve the revision via the button's
    ``value`` (we stamp the revision id there in ``client._build_signoff_blocks``),
    flip the status, and update the original message so the buttons disappear.
    """
    body = await _verify_slack_request(
        request, x_slack_signature, x_slack_request_timestamp
    )

    form = parse_qs(body.decode("utf-8"))
    raw_payload = form.get("payload", [""])[0]
    if not raw_payload:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "missing interaction payload"
        )

    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"invalid payload JSON: {exc}"
        ) from exc

    if payload.get("type") != "block_actions":
        # Other interaction types (view submissions, shortcuts) aren't wired
        # up in v0.3 — ack so Slack doesn't retry.
        return {"ok": True}

    actions = payload.get("actions") or []
    if not actions:
        return {"ok": True}
    action = actions[0]
    action_id = action.get("action_id", "")
    revision_id = action.get("value")

    if action_id not in {
        "litmus_signoff_approve",
        "litmus_signoff_reject",
    }:
        return {"ok": True}

    if not revision_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "missing revision id in action value"
        )

    revision = (
        session.query(MetricRevision)
        .join(Metric, MetricRevision.metric_id == Metric.id)
        .filter(MetricRevision.id == revision_id, Metric.org_id == org.id)
        .one_or_none()
    )
    if revision is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "revision not found")

    user = payload.get("user") or {}
    # Prefer the email (stable, human-readable) but fall back to Slack user
    # id (always present) so the audit trail is never empty.
    actor = user.get("username") or user.get("id") or "slack-user"

    new_status = (
        "approved"
        if action_id == "litmus_signoff_approve"
        else "rejected"
    )
    revision.signoff_status = new_status
    revision.signoff_by = actor
    revision.signoff_at = datetime.utcnow()
    session.flush()
    session.commit()

    # Best-effort update of the original Slack message. Falls through silently
    # if we don't have a bot token configured (webhook-only deployments).
    webhook_url = os.environ.get(_WEBHOOK_URL_ENV, "")
    updated_text = f":white_check_mark: {new_status.capitalize()} by <@{user.get('id', '?')}>"
    slack_client.update_message(
        webhook_url,
        revision.slack_channel_id,
        revision.slack_message_ts,
        text=updated_text,
        blocks=[
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": updated_text},
            }
        ],
    )

    return {"ok": True, "status": new_status, "revision_id": revision.id}


# ── /slack/signoff/request (internal) ─────────────────────────────────


class SignoffRequestIn(BaseModel):
    revision_id: str = Field(..., description="MetricRevision.id to request sign-off for")
    diff_summary: str | None = Field(
        default=None,
        description="Optional human-readable diff to include in the Slack message",
    )


@router.post("/signoff/request")
def slack_signoff_request(
    payload: SignoffRequestIn,
    org: Org = Depends(current_org),
    session: Session = Depends(db_session),
) -> dict[str, Any]:
    """Internal endpoint: post a sign-off prompt for an existing revision.

    Invoked by the upsert path when a new revision lands with
    ``signoff_required=True``. Idempotent — callers are free to retry; we
    always post a fresh Slack message and update the stored
    ``slack_message_ts`` / ``slack_channel_id`` on the revision row.

    This is a normal API route (authed via ``current_org``) so the same path
    also works as a manual "re-notify" button in the UI.
    """
    revision = (
        session.query(MetricRevision)
        .join(Metric, MetricRevision.metric_id == Metric.id)
        .filter(MetricRevision.id == payload.revision_id, Metric.org_id == org.id)
        .one_or_none()
    )
    if revision is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "revision not found")

    metric = session.get(Metric, revision.metric_id)
    if metric is None:  # safety — cascade should have prevented this
        raise HTTPException(status.HTTP_404_NOT_FOUND, "metric not found")

    revision.signoff_required = True
    if revision.signoff_status not in {"pending", "approved", "rejected", "auto_approved"}:
        revision.signoff_status = "pending"
    session.flush()

    result = _post_signoff_to_slack(
        session, metric, revision, diff_summary=payload.diff_summary
    )
    session.commit()
    return {
        "ok": result.get("ok", False),
        "revision_id": revision.id,
        "message_ts": revision.slack_message_ts,
        "channel_id": revision.slack_channel_id,
    }


# ── shared helper ─────────────────────────────────────────────────────


def _post_signoff_to_slack(
    session: Session,
    metric: Metric,
    revision: MetricRevision,
    *,
    diff_summary: str | None = None,
) -> dict[str, Any]:
    """Post a sign-off prompt and persist the Slack message coordinates.

    Returns the Slack response dict so callers can surface ``ok`` state. A
    missing webhook URL is a no-op: we log and return a sentinel rather than
    crashing — the upsert path MUST not fail because Slack isn't configured.
    """
    webhook_url = os.environ.get(_WEBHOOK_URL_ENV)
    if not webhook_url:
        logger.info(
            "Slack webhook URL not configured; skipping signoff post for %s",
            metric.slug,
        )
        return {"ok": False, "error": "slack_not_configured"}

    default_channel = os.environ.get(_DEFAULT_CHANNEL_ENV)

    response = slack_client.post_signoff_message(
        webhook_url,
        revision,
        diff_summary or f"Revision `{revision.id[:8]}` of `{metric.slug}` pending sign-off.",
        default_channel=default_channel,
        metric_name=metric.name,
        metric_slug=metric.slug,
    )

    # Incoming webhooks may not return ts/channel; Web API replies do. Store
    # whatever we got so later updates can try to edit the message in place.
    if response.get("ts"):
        revision.slack_message_ts = response["ts"]
    if response.get("channel"):
        revision.slack_channel_id = response["channel"]
    session.flush()
    return response
