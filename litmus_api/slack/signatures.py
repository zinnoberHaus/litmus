"""Slack request signature verification.

Slack signs every inbound request to our slash-command, interaction, and
Events API endpoints. Verifying that signature is the *only* thing standing
between "an attacker fires approval clicks" and "they don't" — so we
follow the spec literally:

1. Concatenate ``v0:{timestamp}:{body}``.
2. HMAC-SHA256 with ``LITMUS_SLACK_SIGNING_SECRET``.
3. Prefix with ``v0=`` and constant-time compare against ``X-Slack-Signature``.
4. Reject if the timestamp is more than 5 minutes off wall-clock (Slack's
   published replay-protection window).

Mirrors the pattern in ``litmus_api/routes/webhooks.py`` for GitHub — same
shape, different header names.

Reference: https://api.slack.com/authentication/verifying-requests-from-slack
"""

from __future__ import annotations

import hashlib
import hmac
import time

# Slack's own spec says "reject anything older than 5 minutes" to prevent
# replay attacks on a leaked request. We mirror that verbatim.
MAX_TIMESTAMP_AGE_SECONDS = 300


def is_valid_signature(
    signing_secret: str,
    timestamp: str | None,
    body: bytes,
    signature: str | None,
    *,
    now: float | None = None,
) -> bool:
    """Return True iff ``signature`` matches what Slack would have sent.

    All inputs are treated as untrusted. Missing / malformed header values
    fail closed — never silently accept.

    ``now`` is an injection point for tests; production code should leave it
    as None so we use wall-clock time.
    """
    if not signing_secret:
        return False
    if not timestamp or not signature:
        return False
    if not signature.startswith("v0="):
        return False

    # Timestamp must be a plain integer (Slack sends unix seconds). Anything
    # else → malformed → reject. We also reject ages > 5 minutes to block
    # replayed captures of a legitimate request.
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        return False
    current = time.time() if now is None else now
    if abs(current - ts) > MAX_TIMESTAMP_AGE_SECONDS:
        return False

    basestring = f"v0:{timestamp}:".encode() + body
    digest = hmac.new(
        signing_secret.encode("utf-8"), basestring, hashlib.sha256
    ).hexdigest()
    expected = f"v0={digest}"
    return hmac.compare_digest(expected, signature)
