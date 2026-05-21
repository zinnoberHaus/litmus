"""Pipeline orchestration — ingest + transform.

The pipeline runner is deliberately lightweight: YAML specs describe ingest
sources, SQL files describe transforms, and the runner is ~200 lines. Teams
that outgrow it graduate to Dagster / Airflow / Prefect; Litmus is the
zero-to-one tier.
"""

from __future__ import annotations
