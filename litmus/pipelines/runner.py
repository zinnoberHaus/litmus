"""Pipeline runner — ingests and transforms.

Reads pipelines/*.yaml ingest specs and transforms/*.sql transform files,
runs them against the configured warehouse, records run history in the
Litmus history store.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml

PIPELINES_DIR = Path("pipelines")
TRANSFORMS_DIR = Path("transforms")
STATE_FILE = Path(".litmus/state.json")


def list_pipelines() -> list[Path]:
    if not PIPELINES_DIR.exists():
        return []
    return sorted(PIPELINES_DIR.glob("*.yaml"))


def list_transforms() -> list[Path]:
    if not TRANSFORMS_DIR.exists():
        return []
    return sorted(TRANSFORMS_DIR.glob("*.sql"))


def _load_pipeline(name: str) -> dict[str, Any]:
    path = PIPELINES_DIR / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Pipeline not found: {path}")
    loaded: dict[str, Any] = yaml.safe_load(path.read_text())
    return loaded


def _expand_env(value: str) -> str:
    """Expand ${VAR} references in a YAML string field."""
    return os.path.expandvars(value) if isinstance(value, str) else value


def _connect(warehouse_url: str):
    """Return a DB-API connection for the warehouse URL.

    Only DuckDB is wired here in the v0.1 skeleton. Postgres / Snowflake
    / BigQuery delegate to Litmus's connectors in a follow-up.
    """
    if warehouse_url.startswith("duckdb://"):
        import duckdb

        path = warehouse_url.replace("duckdb:///", "").replace("duckdb://", "")
        return duckdb.connect(path)
    raise NotImplementedError(
        f"Warehouse {warehouse_url} not yet wired in litmus.pipelines.runner — "
        "use Litmus connectors directly for non-DuckDB targets."
    )


def _default_warehouse() -> str:
    """Resolve the warehouse URL using this precedence:
    1. Explicit env var (LITMUS_WAREHOUSE_URL)
    2. Project state file (.litmus/state.json: warehouse_url)
    3. Local DuckDB fallback (works zero-config)
    """
    env = os.environ.get("LITMUS_WAREHOUSE_URL")
    if env:
        return env

    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text())
            url = state.get("warehouse_url")
            if url:
                return str(url)
        except (json.JSONDecodeError, OSError):
            pass

    return "duckdb:///./data/warehouse.duckdb"


def run_ingest(name: str, warehouse_url: str | None = None) -> int:
    """Run a single ingest pipeline. Returns the number of rows loaded."""
    spec = _load_pipeline(name)
    warehouse_url = warehouse_url or _default_warehouse()
    con = _connect(warehouse_url)

    source = spec["source"]
    target = spec["target"]
    table = target["table"]
    mode = target.get("mode", "append")

    if source["type"] == "csv":
        path = _expand_env(source["path"])
        select_with_loaded_at = (
            "SELECT *, CURRENT_TIMESTAMP AS _loaded_at FROM read_csv_auto(?)"
        )
        if mode == "replace":
            con.execute(
                f"CREATE OR REPLACE TABLE {table} AS {select_with_loaded_at}",
                [path],
            )
        else:
            con.execute(
                f"CREATE TABLE IF NOT EXISTS {table} AS "
                f"{select_with_loaded_at} WHERE 1=0",
                [path],
            )
            con.execute(
                f"INSERT INTO {table} {select_with_loaded_at}",
                [path],
            )
        rows = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    else:
        raise NotImplementedError(
            f"Ingest source type '{source['type']}' not yet implemented in v0.1 — "
            "currently only 'csv' is supported. PRs welcome."
        )

    print(f"[ingest] {name}: loaded {rows:,} rows into {table}")
    return int(rows)


def run_transform(name: str, warehouse_url: str | None = None) -> int:
    """Run a single transform. Returns the row count of the resulting table."""
    path = TRANSFORMS_DIR / f"{name}.sql"
    if not path.exists():
        raise FileNotFoundError(f"Transform not found: {path}")

    warehouse_url = warehouse_url or _default_warehouse()
    con = _connect(warehouse_url)

    sql = path.read_text()
    con.execute(sql)

    # Heuristic: try to count rows in a table matching the file stem.
    try:
        rows = con.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
        print(f"[transform] {name}: {rows:,} rows in {name}")
        return int(rows)
    except Exception:
        print(f"[transform] {name}: complete (row count unavailable)")
        return -1


def run_all(warehouse_url: str | None = None) -> None:
    """Run every pipeline + every transform."""
    warehouse_url = warehouse_url or _default_warehouse()

    for p in list_pipelines():
        run_ingest(p.stem, warehouse_url)
    for t in list_transforms():
        run_transform(t.stem, warehouse_url)
