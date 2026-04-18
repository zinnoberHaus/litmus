from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch) -> Iterator[TestClient]:
    """Fresh FastAPI app backed by a temp SQLite file, reset per test."""
    db_path = tmp_path / "litmus_api.db"
    monkeypatch.setenv("LITMUS_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("LITMUS_TENANT_MODE", "single")

    # Reset db module-level state so each test gets its own engine.
    import litmus_api.db as db_mod

    db_mod._engine = None
    db_mod._SessionLocal = None

    from litmus_api.main import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c
