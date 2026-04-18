"""Minimal Slack outbound client — webhook-only, stdlib-only.

Two ways we post to Slack:

1. **Incoming webhook URL** (``LITMUS_SLACK_WEBHOOK_URL``). One URL → one
   channel. This is the MVP distribution path — operators create a Slack
   app in *their* workspace, drop the URL into our server's env, and we
   can post without OAuth, scopes, or a Marketplace listing.

2. **Web API** (``chat.postMessage`` / ``chat.update``). Used when we need
   to update a previously-posted message (e.g. flip "Approve/Reject" buttons
   to "Approved by @alice" after a click). Requires a bot token — a full
   Slack App feature deferred to v0.4. For v0.3 we gracefully degrade:
   ``update_message`` is a no-op unless ``LITMUS_SLACK_BOT_TOKEN`` is set.

We use ``urllib.request`` rather than ``requests`` or ``slack-sdk`` to stay
zero-dep, matching ``litmus/api_push.py`` and the GitHub webhook handler.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

# 8 seconds keeps us well inside Slack's 3-second handshake for inbound
# requests while still giving time for the outbound POST to finish.
_TIMEOUT_SECONDS = 8


def _post_json(
    url: str, payload: dict[str, Any], *, headers: dict[str, str] | None = None
) -> dict[str, Any]:
    """POST ``payload`` as JSON and return the parsed response body.

    Slack incoming webhooks reply with a plain ``ok`` (text body), while the
    Web API replies with JSON. We try JSON first; falling back to a shimmed
    dict keeps the caller's contract uniform.
    """
    data = json.dumps(payload).encode("utf-8")
    req_headers = {
        "Content-Type": "application/json; charset=utf-8",
        "User-Agent": os.environ.get(
            "LITMUS_SLACK_BOT_USER_AGENT", "litmus-slack/0.3"
        ),
    }
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, data=data, headers=req_headers, method="POST")
    with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:
        body = resp.read().decode("utf-8")

    if not body:
        return {"ok": True}
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        # Incoming webhooks reply with literal "ok" — not JSON. Normalize.
        return {"ok": body.strip().lower() == "ok", "raw": body}


def post_signoff_message(
    webhook_url: str,
    revision: Any,
    diff_summary: str,
    *,
    default_channel: str | None = None,
    metric_name: str | None = None,
    metric_slug: str | None = None,
) -> dict[str, Any]:
    """Post the sign-off prompt to Slack.

    Returns the Slack response dict. Callers that need the ``message_ts`` /
    ``channel_id`` (to persist on the revision row for later updates) should
    read ``response.get("ts")`` and ``response.get("channel")``. Both are
    best-effort — incoming webhook mode may not return a ``ts`` at all, in
    which case we persist ``None`` and later updates fall through to a
    new-message path.
    """
    blocks = _build_signoff_blocks(
        revision=revision,
        diff_summary=diff_summary,
        metric_name=metric_name,
        metric_slug=metric_slug,
    )
    payload: dict[str, Any] = {
        "text": f"Metric sign-off requested: {metric_name or metric_slug or 'unknown'}",
        "blocks": blocks,
    }
    if default_channel:
        payload["channel"] = default_channel

    try:
        return _post_json(webhook_url, payload)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        # Slack failures must NEVER break the catalog upsert. Log loudly so
        # operators can trace it, but propagate a sentinel the caller can
        # check without raising.
        logger.warning("Slack signoff post failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def post_message(
    channel: str | None,
    text: str,
    *,
    blocks: list[dict[str, Any]] | None = None,
    thread_ts: str | None = None,
    webhook_url: str | None = None,
    bot_token: str | None = None,
) -> dict[str, Any]:
    """Post a plain message to Slack.

    Two delivery paths:

    1. **Bot token** (``LITMUS_SLACK_BOT_TOKEN``) — preferred when we need to
       post to a channel the ``app_mention`` event came from. Hits
       ``chat.postMessage``, which respects ``thread_ts`` so replies land in
       the same thread as the mention.
    2. **Incoming webhook** (``LITMUS_SLACK_WEBHOOK_URL``) — fallback for
       deployments that only configured the MVP webhook path. Can't scope to
       a channel at runtime; fires into whatever channel the webhook is
       bound to in the Slack app config.

    Failures are swallowed and returned as a sentinel dict — the caller
    (the ``app_mention`` handler) must never raise into Slack's event loop.
    """
    if bot_token is None:
        bot_token = os.environ.get("LITMUS_SLACK_BOT_TOKEN")
    if webhook_url is None:
        webhook_url = os.environ.get("LITMUS_SLACK_WEBHOOK_URL")

    payload: dict[str, Any] = {"text": text}
    if blocks is not None:
        payload["blocks"] = blocks
    if thread_ts:
        payload["thread_ts"] = thread_ts

    try:
        if bot_token and channel:
            payload["channel"] = channel
            return _post_json(
                "https://slack.com/api/chat.postMessage",
                payload,
                headers={"Authorization": f"Bearer {bot_token}"},
            )
        if webhook_url:
            # Incoming webhooks ignore ``channel`` but accept ``text``/``blocks``.
            return _post_json(webhook_url, payload)
        return {"ok": False, "error": "no_slack_delivery_configured"}
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        logger.warning("Slack post_message failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def update_message(
    webhook_url_or_api: str,
    channel_id: str | None,
    ts: str | None,
    text: str,
    blocks: list[dict[str, Any]] | None = None,
    *,
    bot_token: str | None = None,
) -> dict[str, Any]:
    """Update a previously-posted message.

    In v0.3 we require a bot token for updates — Slack's incoming-webhook
    URLs are write-once (no update support). If no token is configured we
    return a no-op response so the interaction handler can still 200 without
    failing the whole flow.
    """
    if not bot_token:
        bot_token = os.environ.get("LITMUS_SLACK_BOT_TOKEN")
    if not bot_token or not ts or not channel_id:
        return {"ok": False, "error": "update requires bot token + channel + ts"}

    payload: dict[str, Any] = {
        "channel": channel_id,
        "ts": ts,
        "text": text,
    }
    if blocks is not None:
        payload["blocks"] = blocks

    try:
        return _post_json(
            "https://slack.com/api/chat.update",
            payload,
            headers={"Authorization": f"Bearer {bot_token}"},
        )
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        logger.warning("Slack chat.update failed: %s", exc)
        return {"ok": False, "error": str(exc)}


_TRUST_EMOJI: dict[str, str] = {
    "passed": ":large_green_circle:",
    "warning": ":large_yellow_circle:",
    "failed": ":red_circle:",
    "error": ":red_circle:",
    "unknown": ":white_circle:",
}


def build_ask_answer_blocks(
    *,
    answer: str,
    metric_name: str | None,
    metric_slug: str,
    trust_status: str,
    metric_url: str | None,
    explanation: str | None = None,
) -> list[dict[str, Any]]:
    """Build the Block Kit payload for an answered Slack ``/ask`` or mention.

    Layout: a one-line summary (emoji + bold metric name) on top, the full
    answer as a mrkdwn section, then a context footer with a link back to the
    metric detail page. If the caller didn't configure a ``LITMUS_PUBLIC_URL``
    we skip the link and keep the card self-contained.
    """
    emoji = _TRUST_EMOJI.get(trust_status, _TRUST_EMOJI["unknown"])
    header_label = metric_name or metric_slug
    blocks: list[dict[str, Any]] = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"{emoji} *{header_label}* — trust: `{trust_status}`",
            },
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": answer},
        },
    ]
    if explanation:
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f":information_source: {explanation}"}
                ],
            }
        )
    if metric_url and metric_url.startswith(("http://", "https://")):
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"<{metric_url}|View metric definition>",
                    }
                ],
            }
        )
    return blocks


def _build_signoff_blocks(
    *,
    revision: Any,
    diff_summary: str,
    metric_name: str | None,
    metric_slug: str | None,
) -> list[dict[str, Any]]:
    """Build the Block Kit payload for the sign-off prompt.

    ``revision`` is a ``MetricRevision`` row (or anything with an ``id``
    attribute) — we only pull ``revision.id`` to stamp it into the button
    action_ids so the interaction handler knows which row to update.
    """
    revision_id = getattr(revision, "id", "unknown")
    header_name = metric_name or metric_slug or "Metric"
    return [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"Sign-off requested: {header_name}",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": diff_summary or "_(no diff summary provided)_",
            },
        },
        {
            "type": "actions",
            "block_id": f"litmus_signoff_{revision_id}",
            "elements": [
                {
                    "type": "button",
                    "action_id": "litmus_signoff_approve",
                    "style": "primary",
                    "text": {"type": "plain_text", "text": "Approve"},
                    "value": revision_id,
                },
                {
                    "type": "button",
                    "action_id": "litmus_signoff_reject",
                    "style": "danger",
                    "text": {"type": "plain_text", "text": "Reject"},
                    "value": revision_id,
                },
            ],
        },
    ]
