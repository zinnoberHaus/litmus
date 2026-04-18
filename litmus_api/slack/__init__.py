"""Slack integration — webhook-only MVP (see REFACTOR_BLUEPRINT.md decision 3).

v0.3 ships two flows:

1. **Outbound** — when a new ``MetricRevision`` lands with
   ``signoff_required=True``, we post a Block Kit message to
   ``LITMUS_SLACK_WEBHOOK_URL`` with Approve / Reject buttons. The message
   ``ts`` and ``channel_id`` are persisted on the revision row so a later
   button press can update the original message.

2. **Inbound** — Slack POSTs slash commands, interactions, and Events API
   payloads to ``/api/v1/slack/*``. Every request is HMAC-verified against
   ``LITMUS_SLACK_SIGNING_SECRET`` before we touch any state.

Full Slack App distribution (OAuth, Marketplace) is deferred to v0.4. The
routes and signature verification are scaffolded now so the upgrade is
additive, not a rewrite.
"""
