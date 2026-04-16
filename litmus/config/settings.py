"""Config file handling for litmus.yml."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class WarehouseConfig:
    type: str = "duckdb"
    database: str = ":memory:"
    host: str | None = None
    port: int | None = None
    schema: str = "public"
    account: str | None = None
    warehouse: str | None = None
    role: str | None = None

    @property
    def user(self) -> str | None:
        return os.environ.get("LITMUS_WAREHOUSE_USER")

    @property
    def password(self) -> str | None:
        return os.environ.get("LITMUS_WAREHOUSE_PASSWORD")


@dataclass
class DefaultsConfig:
    freshness: str = "24 hours"
    null_rate: str = "5%"
    volume_change: str = "25%"


@dataclass
class ReportingConfig:
    format: str = "console"
    colors: bool = True


@dataclass
class LitmusConfig:
    version: int = 1
    metrics_dir: str = "metrics/"
    warehouse: WarehouseConfig = field(default_factory=WarehouseConfig)
    defaults: DefaultsConfig = field(default_factory=DefaultsConfig)
    reporting: ReportingConfig = field(default_factory=ReportingConfig)

    @property
    def metrics_path(self) -> Path:
        return Path(self.metrics_dir)


def load_config(path: str | Path | None = None) -> LitmusConfig:
    """Load a litmus.yml config file. Falls back to defaults if not found."""
    if path is None:
        path = Path("litmus.yml")
    else:
        path = Path(path)

    if not path.exists():
        return LitmusConfig()

    with open(path) as f:
        raw = yaml.safe_load(f) or {}

    wh_data = raw.get("warehouse", {})
    warehouse = WarehouseConfig(
        type=wh_data.get("type", "duckdb"),
        database=wh_data.get("database", ":memory:"),
        host=wh_data.get("host"),
        port=wh_data.get("port"),
        schema=wh_data.get("schema", "public"),
        account=wh_data.get("account"),
        warehouse=wh_data.get("warehouse"),
        role=wh_data.get("role"),
    )

    defaults_data = raw.get("defaults", {})
    defaults = DefaultsConfig(
        freshness=str(defaults_data.get("freshness", "24 hours")),
        null_rate=str(defaults_data.get("null_rate", "5%")),
        volume_change=str(defaults_data.get("volume_change", "25%")),
    )

    reporting_data = raw.get("reporting", {})
    reporting = ReportingConfig(
        format=reporting_data.get("format", "console"),
        colors=reporting_data.get("colors", True),
    )

    return LitmusConfig(
        version=raw.get("version", 1),
        metrics_dir=raw.get("metrics_dir", "metrics/"),
        warehouse=warehouse,
        defaults=defaults,
        reporting=reporting,
    )


def get_connector(config: LitmusConfig):
    """Create the appropriate connector based on config."""
    wh = config.warehouse
    if wh.type == "duckdb":
        from litmus.connectors.duckdb import DuckDBConnector
        return DuckDBConnector(database=wh.database)
    elif wh.type == "sqlite":
        from litmus.connectors.sqlite import SQLiteConnector
        return SQLiteConnector(database=wh.database)
    elif wh.type == "postgres":
        from litmus.connectors.postgres import PostgresConnector
        return PostgresConnector(
            host=wh.host or "localhost",
            port=wh.port or 5432,
            database=wh.database,
            user=wh.user or "",
            password=wh.password or "",
            schema=wh.schema,
        )
    elif wh.type == "snowflake":
        from litmus.connectors.snowflake import SnowflakeConnector
        return SnowflakeConnector(
            account=wh.account or "",
            user=wh.user or "",
            password=wh.password or "",
            database=wh.database,
            schema=wh.schema,
            warehouse=wh.warehouse,
            role=wh.role,
        )
    elif wh.type == "bigquery":
        from litmus.connectors.bigquery import BigQueryConnector
        return BigQueryConnector(
            project=wh.database,
            dataset=wh.schema,
        )
    else:
        raise ValueError(f"Unknown warehouse type: {wh.type}")
