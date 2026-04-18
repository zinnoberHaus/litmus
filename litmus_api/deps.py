from __future__ import annotations

import hashlib
from collections.abc import Iterator
from datetime import datetime

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from litmus_api.config import Settings, get_settings
from litmus_api.db import get_session
from litmus_api.models import ApiKey, Org, ensure_default_org


def _hash_key(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def db_session() -> Iterator[Session]:
    yield from get_session()


def current_org(
    authorization: str | None = Header(default=None),
    session: Session = Depends(db_session),
    settings: Settings = Depends(get_settings),
) -> Org:
    """Resolve the acting org.

    Single-tenant mode: if no key is present we fall back to the default org.
    Multi-tenant mode: an API key is required and must resolve to an org.
    """
    if authorization:
        token = authorization.removeprefix("Bearer ").strip()
        if not token:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Empty bearer token")
        key = (
            session.query(ApiKey)
            .filter_by(hash=_hash_key(token), revoked_at=None)
            .one_or_none()
        )
        if key is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")
        key.last_used_at = datetime.utcnow()
        session.flush()
        org = session.get(Org, key.org_id)
        if org is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Orphaned API key")
        return org

    if settings.tenant_mode != "single":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "API key required")
    return ensure_default_org(session, settings.default_org_slug)
