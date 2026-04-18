"""GitHub webhook ingestion.

Accepts ``push`` events from GitHub, pulls any ``.metric`` files that were
added or modified in the push, and upserts them into the catalog. This is
the "no code change needed" onboarding path — point your repo's webhook at
``/webhooks/github``, drop a ``.metric`` file into the tree, push, and the
metric shows up in the catalog.

Public repos only. Private repos need the GitHub App OAuth flow which the
OSS wedge deliberately does not ship — we document the limitation in
``docs/github-webhook.md``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import urllib.error
import urllib.request
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from litmus.parser.errors import LitmusParseError
from litmus_api.deps import current_org, db_session
from litmus_api.models import Org
from litmus_api.routes.metrics import MetricUpsertIn, _perform_upsert

router = APIRouter(tags=["webhooks"])


_GITHUB_SECRET_ENV = "LITMUS_GITHUB_WEBHOOK_SECRET"
_RAW_URL_TEMPLATE = "https://raw.githubusercontent.com/{repo}/{sha}/{path}"


def _verify_signature(secret: str, body: bytes, signature: str | None) -> bool:
    """Constant-time verify of the ``X-Hub-Signature-256`` header.

    GitHub signs the raw body with HMAC-SHA256 and prefixes the hex digest
    with ``sha256=``. An empty or missing header → fail closed.
    """
    if not signature or not signature.startswith("sha256="):
        return False
    expected = (
        "sha256="
        + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    )
    return hmac.compare_digest(expected, signature)


def _collect_metric_paths(commits: list[dict[str, Any]]) -> list[str]:
    """Union of ``added`` and ``modified`` paths across every commit, filtered
    to ``.metric`` files. Order preserved, duplicates collapsed.
    """
    seen: set[str] = set()
    out: list[str] = []
    for commit in commits:
        for key in ("added", "modified"):
            for path in commit.get(key, []) or []:
                if not isinstance(path, str) or not path.endswith(".metric"):
                    continue
                if path in seen:
                    continue
                seen.add(path)
                out.append(path)
    return out


def _fetch_raw(repo: str, sha: str, path: str) -> str:
    """Fetch a file at a specific commit from ``raw.githubusercontent.com``.

    We use stdlib ``urllib.request`` so the webhook path has zero extra deps
    — same constraint ``litmus/api_push.py`` works under. Public repos only.
    """
    url = _RAW_URL_TEMPLATE.format(repo=repo, sha=sha, path=path)
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8")


@router.post("/webhooks/github")
async def github_webhook(
    request: Request,
    x_github_event: str | None = Header(default=None),
    x_hub_signature_256: str | None = Header(default=None),
    org: Org = Depends(current_org),
    session: Session = Depends(db_session),
) -> dict[str, Any]:
    """Ingest a GitHub webhook.

    We read the raw body first so the HMAC check sees exactly what GitHub
    signed — ``await request.json()`` would re-serialize and break parity.
    """
    secret = os.environ.get(_GITHUB_SECRET_ENV)
    if not secret:
        # Fail closed if the operator hasn't configured the secret. Returning
        # 401 (rather than 500) keeps the surface minimal from GitHub's side
        # — its delivery UI just shows "unauthorized" and the operator fixes
        # the env var.
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            f"{_GITHUB_SECRET_ENV} is not configured on the server",
        )

    body = await request.body()
    if not _verify_signature(secret, body, x_hub_signature_256):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "invalid signature"
        )

    # Everything below here is authenticated. Non-push events are a no-op —
    # we still 200 so GitHub doesn't disable the hook after repeated 4xxs.
    if x_github_event != "push":
        return {"status": "ignored"}

    try:
        payload = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"invalid JSON body: {exc}"
        ) from exc

    repo = (payload.get("repository") or {}).get("full_name")
    head_commit = payload.get("head_commit") or {}
    head_sha = head_commit.get("id")
    author_email = ((head_commit.get("author") or {}).get("email")) or None
    commits = payload.get("commits") or []

    if not repo or not head_sha:
        # The push event is malformed — we can't fetch files without both.
        return {"upserted": [], "ignored": []}

    metric_paths = _collect_metric_paths(commits)
    upserted: list[str] = []
    ignored: list[str] = []

    for path in metric_paths:
        try:
            spec_text = _fetch_raw(repo, head_sha, path)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
            # A 404 here usually means the file was deleted in a later commit
            # on the same push, or the repo is private. Either way we skip —
            # the webhook is advisory, not authoritative.
            ignored.append(path)
            continue

        upsert_payload = MetricUpsertIn(
            spec_text=spec_text,
            source_repo=repo,
            source_path=path,
            source_sha=head_sha,
            author=author_email,
        )
        try:
            metric = _perform_upsert(session, org, upsert_payload)
        except LitmusParseError:
            # Broken ``.metric`` file — don't fail the whole push, just flag
            # the path in the response so the operator can find it.
            ignored.append(path)
            continue
        upserted.append(metric.slug)

    session.commit()
    return {"upserted": upserted, "ignored": ignored}
