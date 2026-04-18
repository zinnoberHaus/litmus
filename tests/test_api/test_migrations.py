"""Lock in the invariant that ``alembic upgrade head`` produces the same
schema as ``Base.metadata.create_all`` on a fresh DB.

If these drift, it means somebody changed a model without shipping a
migration — catching that in tests is cheaper than catching it in prod.
"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, inspect

import litmus_api.db as db_mod
from litmus_api.db import get_engine, init_engine
from litmus_api.models import Base

_MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "litmus_api" / "migrations"


def _run_alembic_upgrade(url: str) -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(_MIGRATIONS_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(_MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")


def _reset_engine(url: str) -> None:
    db_mod._engine = None
    db_mod._SessionLocal = None
    os.environ["LITMUS_DATABASE_URL"] = url
    init_engine()


def _tables(url: str, *, exclude_alembic: bool = False) -> set[str]:
    engine = create_engine(url)
    try:
        tables = set(inspect(engine).get_table_names())
        if exclude_alembic:
            tables.discard("alembic_version")
        return tables
    finally:
        engine.dispose()


def test_alembic_head_tables_match_metadata_create_all(tmp_path) -> None:
    # create_all reference
    ref_url = f"sqlite:///{tmp_path / 'ref.db'}"
    _reset_engine(ref_url)
    Base.metadata.create_all(bind=get_engine())

    # alembic candidate
    cand_url = f"sqlite:///{tmp_path / 'cand.db'}"
    _run_alembic_upgrade(cand_url)

    ref_tables = _tables(ref_url)
    cand_tables = _tables(cand_url, exclude_alembic=True)

    assert ref_tables == cand_tables, (
        "create_all vs alembic upgrade head produced different tables: "
        f"extra in create_all={ref_tables - cand_tables} "
        f"extra in alembic={cand_tables - ref_tables}"
    )


def test_alembic_head_columns_match_metadata_create_all(tmp_path) -> None:
    ref_url = f"sqlite:///{tmp_path / 'ref.db'}"
    _reset_engine(ref_url)
    Base.metadata.create_all(bind=get_engine())

    cand_url = f"sqlite:///{tmp_path / 'cand.db'}"
    _run_alembic_upgrade(cand_url)

    ref_engine = create_engine(ref_url)
    cand_engine = create_engine(cand_url)
    try:
        ref_i = inspect(ref_engine)
        cand_i = inspect(cand_engine)
        for table in sorted(set(ref_i.get_table_names())):
            if table == "alembic_version":
                continue
            ref_cols = {
                (c["name"], str(c["type"]), c["nullable"])
                for c in ref_i.get_columns(table)
            }
            cand_cols = {
                (c["name"], str(c["type"]), c["nullable"])
                for c in cand_i.get_columns(table)
            }
            assert ref_cols == cand_cols, (
                f"column mismatch for table {table!r}: "
                f"create_all={ref_cols} alembic={cand_cols}"
            )
    finally:
        ref_engine.dispose()
        cand_engine.dispose()
