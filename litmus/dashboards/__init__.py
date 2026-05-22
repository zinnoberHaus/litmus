"""Streamlit dashboard helpers — a freshness header.

Imported by dashboard scaffolds so the freshness pattern is consistent across
the project. Streamlit is an optional dependency; functions no-op gracefully if
streamlit isn't installed.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path


def _streamlit():
    try:
        import streamlit as st
        return st
    except ImportError:
        return None


def _warehouse_path() -> str:
    url = os.environ.get("LITMUS_WAREHOUSE_URL", "duckdb:///./data/warehouse.duckdb")
    return url.replace("duckdb:///", "").replace("duckdb://", "")


def freshness_header(tables: Iterable[str]) -> None:
    """Render a 'Data through <timestamp>' line for the given tables."""
    st = _streamlit()
    if st is None:
        return

    try:
        import duckdb
        con = duckdb.connect(_warehouse_path(), read_only=True)
        timestamps = []
        for t in tables:
            row = con.execute(f"SELECT MAX(updated_at) FROM {t}").fetchone()
            if row and row[0]:
                timestamps.append((t, row[0]))
        if timestamps:
            oldest = min(ts for _, ts in timestamps)
            st.caption(f"Data through {oldest:%Y-%m-%d %H:%M} UTC")
    except Exception as e:
        st.caption(f"Data freshness unavailable ({type(e).__name__})")


def data_test_banner(tests_dir: str = "tests") -> None:
    """Render a warning if any ``tests/*.sql`` returns rows (a failing data test).

    Mirrors `litmus test`: a test passes when its query returns zero rows.
    """
    st = _streamlit()
    if st is None:
        return

    sqls = sorted(Path(tests_dir).glob("*.sql")) if Path(tests_dir).exists() else []
    if not sqls:
        return
    try:
        import duckdb
        con = duckdb.connect(_warehouse_path(), read_only=True)
        failing = []
        for s in sqls:
            try:
                if con.execute(s.read_text()).fetchall():
                    failing.append(s.stem)
            except Exception:
                continue
        if failing:
            st.warning(
                "Failing data tests: " + ", ".join(failing) + ". Run `litmus test`."
            )
    except Exception:
        # Test display is best-effort; never block the dashboard.
        pass
