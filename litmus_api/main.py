from __future__ import annotations

from fastapi import FastAPI

from litmus_api import __version__
from litmus_api.db import get_engine, init_engine, session_scope
from litmus_api.models import Base, ensure_default_org
from litmus_api.routes import embeds, metrics, runs


def create_app() -> FastAPI:
    app = FastAPI(
        title="Litmus API",
        version=__version__,
        description="Metric catalog, trust history, and embeddable badges.",
    )

    init_engine()
    Base.metadata.create_all(bind=get_engine())
    with session_scope() as session:
        ensure_default_org(session)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    app.include_router(metrics.router, prefix="/api/v1")
    app.include_router(runs.router, prefix="/api/v1")
    app.include_router(embeds.router)

    return app


app = create_app()
