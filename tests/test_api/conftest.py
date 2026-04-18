from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch) -> Iterator[TestClient]:
    """Fresh FastAPI app backed by a temp SQLite file, reset per test.

    We deliberately skip Alembic here and call ``Base.metadata.create_all``
    instead — running ``alembic upgrade head`` on every test would cost
    hundreds of milliseconds per case and add no coverage, since the
    initial migration is verified to match ``create_all`` in a dedicated
    migration test.
    """
    db_path = tmp_path / "litmus_api.db"
    monkeypatch.setenv("LITMUS_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("LITMUS_TENANT_MODE", "single")
    monkeypatch.delenv("LITMUS_AUTO_MIGRATE", raising=False)

    # Reset db module-level state so each test gets its own engine.
    import litmus_api.db as db_mod

    db_mod._engine = None
    db_mod._SessionLocal = None

    # Pre-create all tables so the ensure_default_org() call inside
    # create_app() has something to insert into. create_app's own
    # init_schema() will no-op for a file-backed URL with LITMUS_AUTO_MIGRATE
    # unset, which is exactly what we want for tests.
    from litmus_api.db import get_engine, init_engine
    from litmus_api.models import Base

    init_engine()
    Base.metadata.create_all(bind=get_engine())

    from litmus_api.main import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c
