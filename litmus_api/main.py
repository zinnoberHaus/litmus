from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI

from litmus_api import __version__
from litmus_api.config import get_settings
from litmus_api.db import get_engine, init_engine, session_scope
from litmus_api.models import Base, ensure_default_org
from litmus_api.routes import embeds, metrics, runs, webhooks

_MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def _is_inmemory_sqlite(url: str) -> bool:
    """Pure in-memory SQLite DSNs — used by the test suite only."""
    return url.startswith("sqlite:///:memory:") or url in {
        "sqlite://",
        "sqlite:///",
    }


def _run_alembic_upgrade(database_url: str) -> None:
    """Programmatic equivalent of ``alembic upgrade head``.

    Kept local so the server process can self-heal at startup when
    ``LITMUS_AUTO_MIGRATE=true`` is set. The recommended path in production
    is still to run ``alembic -c litmus_api/migrations/alembic.ini upgrade head``
    as a separate step before the server starts.
    """
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(_MIGRATIONS_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(_MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(cfg, "head")


def init_schema() -> None:
    """Prepare the catalog DB.

    Precedence:
      1. In-memory SQLite (test-only)    -> ``create_all`` (no migration overhead)
      2. ``LITMUS_AUTO_MIGRATE=true``    -> ``alembic upgrade head``
      3. Default                         -> leave schema alone; ops must have run
                                            ``alembic upgrade head`` beforehand

    The last case intentionally does nothing: in prod we want schema changes
    to be an explicit deploy step, not a side-effect of the process starting.
    """
    settings = get_settings()
    if _is_inmemory_sqlite(settings.database_url):
        Base.metadata.create_all(bind=get_engine())
        return

    if os.getenv("LITMUS_AUTO_MIGRATE", "").lower() in {"1", "true", "yes", "on"}:
        _run_alembic_upgrade(settings.database_url)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Litmus API",
        version=__version__,
        description="Metric catalog, trust history, and embeddable badges.",
    )

    init_engine()
    init_schema()
    with session_scope() as session:
        ensure_default_org(session)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    app.include_router(metrics.router, prefix="/api/v1")
    app.include_router(runs.router, prefix="/api/v1")
    app.include_router(embeds.router)
    # Webhooks are mounted at the root — GitHub's webhook UI writes the URL
    # verbatim and we want it short (``/webhooks/github``, not
    # ``/api/v1/webhooks/github``).
    app.include_router(webhooks.router)

    return app


app = create_app()
