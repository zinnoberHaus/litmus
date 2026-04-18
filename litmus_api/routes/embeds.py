from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import desc
from sqlalchemy.orm import Session

from litmus_api.config import Settings, get_settings
from litmus_api.db import get_session
from litmus_api.embed_svg import render_badge_svg
from litmus_api.models import EmbedKey, Metric, Run

router = APIRouter(tags=["embeds"])


def _unknown_svg(settings: Settings) -> Response:
    svg = render_badge_svg(metric_name="unknown metric", status="unknown")
    cache = (
        f"public, max-age={settings.embed_cache_seconds}, "
        f"s-maxage={settings.embed_cache_seconds}"
    )
    return Response(
        content=svg,
        media_type="image/svg+xml; charset=utf-8",
        headers={
            "Cache-Control": cache,
            "Access-Control-Allow-Origin": "*",
        },
    )


@router.get("/embed/{token}/badge.svg")
def embed_badge(
    token: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Response:
    key: EmbedKey | None = (
        session.query(EmbedKey).filter_by(token=token, revoked_at=None).one_or_none()
    )
    if key is None:
        return _unknown_svg(settings)

    metric: Metric | None = session.get(Metric, key.metric_id)
    if metric is None or metric.deleted_at is not None:
        return _unknown_svg(settings)

    latest: Run | None = (
        session.query(Run)
        .filter_by(metric_id=metric.id)
        .order_by(desc(Run.started_at))
        .first()
    )
    status = latest.status if latest else "unknown"
    trust_score = (
        float(latest.trust_score) if latest and latest.trust_score is not None else None
    )

    svg = render_badge_svg(
        metric_name=metric.name,
        status=status,
        trust_score=trust_score,
    )
    cache = (
        f"public, max-age={settings.embed_cache_seconds}, "
        f"s-maxage={settings.embed_cache_seconds}"
    )
    return Response(
        content=svg,
        media_type="image/svg+xml; charset=utf-8",
        headers={
            "Cache-Control": cache,
            "Access-Control-Allow-Origin": "*",
        },
    )
