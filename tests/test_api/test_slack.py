"""Tests for the Slack routes + signature verification + sign-off flow.

We exercise the full round-trip locally without ever hitting Slack's
servers: :func:`_patch_slack_http` replaces the outbound ``urlopen`` inside
``litmus_api.slack.client`` with a fake that records every call, and inbound
requests are signed in-process with the same HMAC Slack would use.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.parse
from dataclasses import dataclass, field
from textwrap import dedent
from typing import Any

import pytest
from fastapi.testclient import TestClient

from litmus_api.slack.signatures import is_valid_signature

_SIGNING_SECRET = "shhh-slack-secret"
_WEBHOOK_URL = "https://hooks.slack.example/fake"

_VALID_SPEC = dedent("""\
    Metric: Slack Revenue
    Description: Revenue metric exercising the Slack signoff flow
    Owner: data@example.com

    Source: orders

    Given all records from orders table
      And status is "completed"

    When we calculate
      Then sum the amount column

    The result is "Slack Revenue"

    Trust:
      Freshness must be less than 24 hours
""")


# ── helpers ───────────────────────────────────────────────────────────


def _slack_sign(timestamp: str, body: bytes) -> str:
    """Return the ``v0=...`` signature Slack would attach."""
    basestring = f"v0:{timestamp}:".encode() + body
    digest = hmac.new(
        _SIGNING_SECRET.encode("utf-8"), basestring, hashlib.sha256
    ).hexdigest()
    return f"v0={digest}"


def _slack_headers(body: bytes, ts: str | None = None) -> dict[str, str]:
    ts = ts or str(int(time.time()))
    return {
        "X-Slack-Signature": _slack_sign(ts, body),
        "X-Slack-Request-Timestamp": ts,
        "Content-Type": "application/json",
    }


@dataclass
class _SlackHTTPRecorder:
    """Captures every outbound call made via the stdlib patched urlopen."""

    calls: list[dict[str, Any]] = field(default_factory=list)
    response_body: bytes = b'{"ok": true, "ts": "1713200000.001", "channel": "C12345"}'
    status: int = 200

    def __call__(self, req, timeout=None):
        body = req.data or b""
        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception:
            payload = {"_raw": body.decode("utf-8", errors="replace")}
        self.calls.append(
            {
                "url": req.full_url,
                "headers": dict(req.headers),
                "payload": payload,
            }
        )
        return _FakeResponse(self.status, self.response_body)


@dataclass
class _FakeResponse:
    status: int
    body: bytes

    def read(self) -> bytes:
        return self.body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc) -> None:
        return None


@pytest.fixture()
def slack_http(monkeypatch) -> _SlackHTTPRecorder:
    """Patch the Slack client's urlopen and return the recorder."""
    recorder = _SlackHTTPRecorder()
    monkeypatch.setattr(
        "litmus_api.slack.client.urllib.request.urlopen",
        recorder,
    )
    return recorder


@pytest.fixture()
def configured_slack(monkeypatch) -> None:
    monkeypatch.setenv("LITMUS_SLACK_SIGNING_SECRET", _SIGNING_SECRET)
    monkeypatch.setenv("LITMUS_SLACK_WEBHOOK_URL", _WEBHOOK_URL)


# ── signature verification unit tests ─────────────────────────────────


class TestSignatureVerification:
    def test_valid_signature_passes(self) -> None:
        body = b'{"type":"event_callback"}'
        ts = str(int(time.time()))
        sig = _slack_sign(ts, body)
        assert is_valid_signature(_SIGNING_SECRET, ts, body, sig)

    def test_invalid_signature_fails(self) -> None:
        body = b'{"type":"event_callback"}'
        ts = str(int(time.time()))
        assert not is_valid_signature(
            _SIGNING_SECRET, ts, body, "v0=not-a-real-digest"
        )

    def test_stale_timestamp_fails(self) -> None:
        body = b'{"type":"event_callback"}'
        now = time.time()
        stale_ts = str(int(now - 10 * 60))  # 10 minutes old
        sig = _slack_sign(stale_ts, body)
        assert not is_valid_signature(
            _SIGNING_SECRET, stale_ts, body, sig, now=now
        )

    def test_missing_signature_fails(self) -> None:
        assert not is_valid_signature(_SIGNING_SECRET, "0", b"x", None)

    def test_missing_timestamp_fails(self) -> None:
        assert not is_valid_signature(_SIGNING_SECRET, None, b"x", "v0=abc")

    def test_non_numeric_timestamp_fails(self) -> None:
        assert not is_valid_signature(
            _SIGNING_SECRET, "not-a-number", b"x", "v0=abc"
        )

    def test_missing_secret_fails(self) -> None:
        body = b"x"
        ts = str(int(time.time()))
        sig = _slack_sign(ts, body)
        assert not is_valid_signature("", ts, body, sig)

    def test_signature_without_v0_prefix_fails(self) -> None:
        body = b"x"
        ts = str(int(time.time()))
        # Correct HMAC but missing the ``v0=`` prefix Slack always sends
        digest = hmac.new(
            _SIGNING_SECRET.encode("utf-8"),
            f"v0:{ts}:".encode() + body,
            hashlib.sha256,
        ).hexdigest()
        assert not is_valid_signature(_SIGNING_SECRET, ts, body, digest)


# ── /api/v1/slack/events ──────────────────────────────────────────────


class TestEventsEndpoint:
    def test_url_verification_challenge_round_trips(
        self, client: TestClient, configured_slack
    ) -> None:
        body = json.dumps(
            {"type": "url_verification", "challenge": "xyz123"}
        ).encode("utf-8")
        resp = client.post(
            "/api/v1/slack/events",
            content=body,
            headers=_slack_headers(body),
        )
        assert resp.status_code == 200
        assert resp.json() == {"challenge": "xyz123"}

    def test_missing_signing_secret_returns_401(
        self, client: TestClient, monkeypatch
    ) -> None:
        """If the operator forgot to configure the secret we must fail closed."""
        monkeypatch.delenv("LITMUS_SLACK_SIGNING_SECRET", raising=False)
        body = json.dumps({"type": "url_verification", "challenge": "x"}).encode(
            "utf-8"
        )
        resp = client.post(
            "/api/v1/slack/events",
            content=body,
            headers=_slack_headers(body),
        )
        assert resp.status_code == 401

    def test_bad_signature_returns_401(
        self, client: TestClient, configured_slack
    ) -> None:
        body = json.dumps({"type": "url_verification", "challenge": "x"}).encode(
            "utf-8"
        )
        headers = _slack_headers(body)
        headers["X-Slack-Signature"] = "v0=tampered"
        resp = client.post(
            "/api/v1/slack/events", content=body, headers=headers
        )
        assert resp.status_code == 401

    def test_stale_timestamp_returns_401(
        self, client: TestClient, configured_slack
    ) -> None:
        stale = str(int(time.time() - 10 * 60))
        body = json.dumps({"type": "url_verification", "challenge": "x"}).encode(
            "utf-8"
        )
        resp = client.post(
            "/api/v1/slack/events",
            content=body,
            headers=_slack_headers(body, ts=stale),
        )
        assert resp.status_code == 401

    def test_app_mention_event_acks_without_question(
        self, client: TestClient, configured_slack, slack_http: _SlackHTTPRecorder
    ) -> None:
        """An ``app_mention`` with just the bot handle and no question still
        gets a friendly nudge, not a crash."""
        body = json.dumps(
            {
                "type": "event_callback",
                "event": {
                    "type": "app_mention",
                    "text": "<@U0LITMUS>",
                    "channel": "C123",
                    "ts": "1713200000.000100",
                },
            }
        ).encode("utf-8")
        resp = client.post(
            "/api/v1/slack/events",
            content=body,
            headers=_slack_headers(body),
        )
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        # The "mention me with a question" nudge fires even when the ask
        # engine is never invoked.
        assert len(slack_http.calls) == 1
        assert "Mention me" in slack_http.calls[0]["payload"]["text"]

    def test_app_mention_routes_question_to_ask_engine(
        self,
        client: TestClient,
        configured_slack,
        slack_http: _SlackHTTPRecorder,
        monkeypatch,
    ) -> None:
        """The heart of task #54: ``@litmus what was revenue?`` must reach
        the ``ask`` engine with the question stripped of the mention token,
        and the answer must be posted back to the source channel+thread."""
        import litmus_api.ai.ask as ask_mod
        from litmus_api.ai.ask import AskAnswer

        captured: dict[str, Any] = {}

        def _stub(session, org, question, **kwargs):
            captured["question"] = question
            captured["org_slug"] = org.slug
            return AskAnswer(
                answer="Monthly Revenue was 4,218,430. Trust is green.",
                metric_slug="revenue",
                metric_name="Monthly Revenue",
                metric_url="https://litmus.example/metrics/revenue",
                value=4_218_430.0,
                trust_status="passed",
                definition_url="https://litmus.example/metrics/revenue",
                explanation=None,
                run_id="run-xyz",
                time_window="last_period",
                model_id="claude-sonnet-4-6",
            )

        monkeypatch.setattr(ask_mod, "answer_question", _stub)

        body = json.dumps(
            {
                "type": "event_callback",
                "event": {
                    "type": "app_mention",
                    "text": "<@U0LITMUS> what was revenue last month?",
                    "channel": "C123",
                    "ts": "1713200000.000200",
                },
            }
        ).encode("utf-8")
        resp = client.post(
            "/api/v1/slack/events",
            content=body,
            headers=_slack_headers(body),
        )
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

        # Engine received the question sans mention prefix.
        assert captured["question"] == "what was revenue last month?"
        # Exactly one outbound Slack post — the answer.
        assert len(slack_http.calls) == 1
        payload = slack_http.calls[0]["payload"]
        assert "4,218,430" in payload["text"]
        # Threaded reply must target the mention's ts.
        assert payload.get("thread_ts") == "1713200000.000200"
        # Block Kit cards include the trust-status chip.
        blocks = payload.get("blocks") or []
        chip_texts = [
            b.get("text", {}).get("text", "")
            for b in blocks
            if b.get("type") == "section"
        ]
        assert any("passed" in t for t in chip_texts)

    def test_app_mention_posts_friendly_error_on_ask_failure(
        self,
        client: TestClient,
        configured_slack,
        slack_http: _SlackHTTPRecorder,
        monkeypatch,
    ) -> None:
        """Engine raises → user sees a one-liner, NOT a stack trace."""
        import litmus_api.ai.ask as ask_mod
        from litmus_api.ai.ask import AskError

        def _raise(*_a, **_kw):
            raise AskError("ai_not_configured", "no key")

        monkeypatch.setattr(ask_mod, "answer_question", _raise)

        body = json.dumps(
            {
                "type": "event_callback",
                "event": {
                    "type": "app_mention",
                    "text": "<@U0LITMUS> revenue?",
                    "channel": "C123",
                    "ts": "1713200000.000300",
                },
            }
        ).encode("utf-8")
        resp = client.post(
            "/api/v1/slack/events",
            content=body,
            headers=_slack_headers(body),
        )
        # Always 200 — Slack would retry on non-2xx and duplicate the message.
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        assert len(slack_http.calls) == 1
        assert "configured" in slack_http.calls[0]["payload"]["text"]


# ── /api/v1/slack/interactions ────────────────────────────────────────


def _upsert_metric_with_signoff(
    client: TestClient, slug: str = "slack_revenue"
) -> dict[str, Any]:
    """Create a metric via the normal upsert path with sign-off requested."""
    resp = client.post(
        "/api/v1/metrics",
        json={"spec_text": _VALID_SPEC, "slug": slug, "signoff_required": True},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestInteractions:
    def test_approve_button_updates_revision(
        self,
        client: TestClient,
        configured_slack,
        slack_http: _SlackHTTPRecorder,
    ) -> None:
        metric = _upsert_metric_with_signoff(client)
        revisions = client.get(
            f"/api/v1/metrics/{metric['id']}/revisions"
        ).json()
        assert len(revisions) == 1
        revision_id = revisions[0]["id"]

        interaction = {
            "type": "block_actions",
            "user": {"id": "U123", "username": "alice@example.com"},
            "actions": [
                {
                    "action_id": "litmus_signoff_approve",
                    "value": revision_id,
                }
            ],
        }
        body = urllib.parse.urlencode(
            {"payload": json.dumps(interaction)}
        ).encode("utf-8")
        headers = _slack_headers(body)
        headers["Content-Type"] = "application/x-www-form-urlencoded"

        resp = client.post(
            "/api/v1/slack/interactions", content=body, headers=headers
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "approved"
        assert data["revision_id"] == revision_id

    def test_approve_button_surfaces_signoff_fields_in_revision_api(
        self,
        client: TestClient,
        configured_slack,
        slack_http: _SlackHTTPRecorder,
    ) -> None:
        """The UI's <SignoffChip> reads signoff_status off the revision row —
        after an Approve click the API must expose the updated fields."""
        metric = _upsert_metric_with_signoff(client, slug="chip_metric")
        revisions = client.get(
            f"/api/v1/metrics/{metric['id']}/revisions"
        ).json()
        revision_id = revisions[0]["id"]
        # Before the click the status is 'pending' (fire-on-upsert marked it).
        assert revisions[0]["signoff_required"] is True
        assert revisions[0]["signoff_status"] == "pending"

        interaction = {
            "type": "block_actions",
            "user": {"id": "U789", "username": "carol@example.com"},
            "actions": [
                {
                    "action_id": "litmus_signoff_approve",
                    "value": revision_id,
                }
            ],
        }
        body = urllib.parse.urlencode(
            {"payload": json.dumps(interaction)}
        ).encode("utf-8")
        headers = _slack_headers(body)
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        client.post("/api/v1/slack/interactions", content=body, headers=headers)

        after = client.get(
            f"/api/v1/metrics/{metric['id']}/revisions"
        ).json()
        assert after[0]["signoff_status"] == "approved"
        assert after[0]["signoff_by"] == "carol@example.com"
        assert after[0]["signoff_at"] is not None

    def test_reject_button_records_rejection(
        self,
        client: TestClient,
        configured_slack,
        slack_http: _SlackHTTPRecorder,
    ) -> None:
        metric = _upsert_metric_with_signoff(client, slug="rej_metric")
        revisions = client.get(
            f"/api/v1/metrics/{metric['id']}/revisions"
        ).json()
        revision_id = revisions[0]["id"]

        interaction = {
            "type": "block_actions",
            "user": {"id": "U456", "username": "bob@example.com"},
            "actions": [
                {
                    "action_id": "litmus_signoff_reject",
                    "value": revision_id,
                }
            ],
        }
        body = urllib.parse.urlencode(
            {"payload": json.dumps(interaction)}
        ).encode("utf-8")
        headers = _slack_headers(body)
        headers["Content-Type"] = "application/x-www-form-urlencoded"

        resp = client.post(
            "/api/v1/slack/interactions", content=body, headers=headers
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"

    def test_unknown_action_is_acked(
        self, client: TestClient, configured_slack
    ) -> None:
        interaction = {
            "type": "block_actions",
            "user": {"id": "U1"},
            "actions": [{"action_id": "unrelated", "value": "x"}],
        }
        body = urllib.parse.urlencode(
            {"payload": json.dumps(interaction)}
        ).encode("utf-8")
        headers = _slack_headers(body)
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        resp = client.post(
            "/api/v1/slack/interactions", content=body, headers=headers
        )
        # Non-signoff action types just 200 so Slack doesn't retry.
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    def test_missing_payload_is_400(
        self, client: TestClient, configured_slack
    ) -> None:
        body = b""
        headers = _slack_headers(body)
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        resp = client.post(
            "/api/v1/slack/interactions", content=body, headers=headers
        )
        assert resp.status_code == 400


# ── /api/v1/slack/commands ────────────────────────────────────────────


class TestSlashCommands:
    def test_pending_list_when_empty(
        self, client: TestClient, configured_slack
    ) -> None:
        body = urllib.parse.urlencode(
            {"command": "/litmus-signoff", "text": "pending"}
        ).encode("utf-8")
        headers = _slack_headers(body)
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        resp = client.post(
            "/api/v1/slack/commands", content=body, headers=headers
        )
        assert resp.status_code == 200
        assert "No pending" in resp.json()["text"]

    def test_pending_list_after_upsert(
        self,
        client: TestClient,
        configured_slack,
        slack_http: _SlackHTTPRecorder,
    ) -> None:
        _upsert_metric_with_signoff(client, slug="cmd_metric")
        body = urllib.parse.urlencode(
            {"command": "/litmus-signoff", "text": "pending"}
        ).encode("utf-8")
        headers = _slack_headers(body)
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        resp = client.post(
            "/api/v1/slack/commands", content=body, headers=headers
        )
        assert resp.status_code == 200
        assert "cmd_metric" in resp.json()["text"]

    def test_unknown_command_is_ephemeral(
        self, client: TestClient, configured_slack
    ) -> None:
        body = urllib.parse.urlencode({"command": "/nope"}).encode("utf-8")
        headers = _slack_headers(body)
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        resp = client.post(
            "/api/v1/slack/commands", content=body, headers=headers
        )
        assert resp.status_code == 200
        assert resp.json()["response_type"] == "ephemeral"


# ── fire-on-upsert ────────────────────────────────────────────────────


class TestFireOnUpsert:
    def test_upsert_with_signoff_flag_posts_to_slack(
        self,
        client: TestClient,
        configured_slack,
        slack_http: _SlackHTTPRecorder,
    ) -> None:
        resp = client.post(
            "/api/v1/metrics",
            json={
                "spec_text": _VALID_SPEC,
                "slug": "fire_metric",
                "signoff_required": True,
            },
        )
        assert resp.status_code == 201
        # The client should have received exactly one outbound POST — the
        # sign-off prompt.
        assert len(slack_http.calls) == 1
        payload = slack_http.calls[0]["payload"]
        assert "blocks" in payload
        # Block Kit: header + section + actions (Approve + Reject).
        action_block = [b for b in payload["blocks"] if b["type"] == "actions"][0]
        action_ids = {e["action_id"] for e in action_block["elements"]}
        assert action_ids == {
            "litmus_signoff_approve",
            "litmus_signoff_reject",
        }

    def test_upsert_without_signoff_does_not_post(
        self,
        client: TestClient,
        configured_slack,
        slack_http: _SlackHTTPRecorder,
    ) -> None:
        resp = client.post(
            "/api/v1/metrics",
            json={"spec_text": _VALID_SPEC, "slug": "quiet_metric"},
        )
        assert resp.status_code == 201
        assert slack_http.calls == []

    def test_env_kill_switch_fires_for_every_upsert(
        self,
        client: TestClient,
        configured_slack,
        monkeypatch,
        slack_http: _SlackHTTPRecorder,
    ) -> None:
        monkeypatch.setenv("LITMUS_SLACK_SIGNOFF_ALL", "true")
        resp = client.post(
            "/api/v1/metrics",
            json={"spec_text": _VALID_SPEC, "slug": "all_metric"},
        )
        assert resp.status_code == 201
        assert len(slack_http.calls) == 1

    def test_slack_failure_does_not_break_upsert(
        self,
        client: TestClient,
        configured_slack,
        monkeypatch,
    ) -> None:
        """The whole point of the try/except in ``_fire_signoff_hook``."""

        def failing_urlopen(req, timeout=None):
            raise urllib.error.URLError("slack is down")

        import urllib.error  # local import so the fixture is self-contained

        monkeypatch.setattr(
            "litmus_api.slack.client.urllib.request.urlopen",
            failing_urlopen,
        )
        resp = client.post(
            "/api/v1/metrics",
            json={
                "spec_text": _VALID_SPEC,
                "slug": "fail_metric",
                "signoff_required": True,
            },
        )
        # Upsert MUST still succeed — Slack failures are strictly best-effort.
        assert resp.status_code == 201


# ── migration parity (duplicate belt-and-braces check) ────────────────


def test_alembic_schema_still_matches_models(tmp_path) -> None:
    """Belt-and-braces: the dedicated migration test already covers this but
    re-running it here tags the failure to the 0006 migration when it breaks.
    """
    from tests.test_api.test_migrations import (
        test_alembic_head_columns_match_metadata_create_all,
        test_alembic_head_tables_match_metadata_create_all,
    )

    test_alembic_head_tables_match_metadata_create_all(tmp_path)
    test_alembic_head_columns_match_metadata_create_all(tmp_path)
