"""Streamlit dashboard helpers — freshness headers + trust banners.

Imported by every dashboard scaffold so the freshness + trust pattern is
consistent across the project. Streamlit is an optional dependency; functions
no-op gracefully if streamlit isn't installed.
"""

from __future__ import annotations

import os
from collections.abc import Iterable


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


def trust_banner(tables: Iterable[str]) -> None:
    """Render a banner if any Litmus check has FAILED for the given tables."""
    st = _streamlit()
    if st is None:
        return

    try:
        from litmus.integrations.trust import check_table
        failed = []
        for t in tables:
            suite = check_table(t)
            if suite and suite.failed > 0:
                failed.append((t, suite.failed))
        if failed:
            msg = ", ".join(f"{t} ({n})" for t, n in failed)
            st.warning(f"Trust check failed: {msg}. Run `litmus check` for details.")
    except Exception:
        # Trust display is best-effort; never block the dashboard.
        pass
