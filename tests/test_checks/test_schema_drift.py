"""Tests for the schema-drift trust check."""

from __future__ import annotations

from pathlib import Path

from litmus.checks.history import HistoryStore
from litmus.checks.runner import CheckStatus
from litmus.checks.schema_drift import check_schema_drift, fingerprint


def test_fingerprint_is_case_and_order_insensitive():
    a = fingerprint(["Order_ID", "amount", "status"])
    b = fingerprint(["status", "amount", "order_id"])
    assert a == b


def test_passes_when_history_disabled():
    result = check_schema_drift(
        "Revenue", current_columns=["a", "b"], history=None
    )
    assert result.status == CheckStatus.PASSED
    assert "history store disabled" in result.message


def test_errors_when_columns_unavailable(tmp_path: Path):
    store = HistoryStore(path=tmp_path / "h.db")
    store.connect()
    try:
        result = check_schema_drift("Revenue", current_columns=None, history=store)
        assert result.status == CheckStatus.ERROR
    finally:
        store.close()


def test_passes_on_first_run(tmp_path: Path):
    store = HistoryStore(path=tmp_path / "h.db")
    store.connect()
    try:
        result = check_schema_drift(
            "Revenue",
            current_columns=["order_id", "amount", "status"],
            history=store,
        )
        assert result.status == CheckStatus.PASSED
        assert "warming up" in result.message
    finally:
        store.close()


def test_passes_when_schema_unchanged(tmp_path: Path):
    store = HistoryStore(path=tmp_path / "h.db")
    store.connect()
    try:
        fp = fingerprint(["order_id", "amount", "status"])
        store.record(
            "Revenue",
            value_sum=None,
            row_count=None,
            schema_fingerprint=fp,
        )
        result = check_schema_drift(
            "Revenue",
            current_columns=["order_id", "amount", "status"],
            history=store,
        )
        assert result.status == CheckStatus.PASSED
        assert "unchanged" in result.message
    finally:
        store.close()


def test_passes_on_column_reorder(tmp_path: Path):
    store = HistoryStore(path=tmp_path / "h.db")
    store.connect()
    try:
        fp = fingerprint(["order_id", "amount", "status"])
        store.record("Revenue", value_sum=None, row_count=None, schema_fingerprint=fp)
        # Same columns, different order
        result = check_schema_drift(
            "Revenue",
            current_columns=["status", "order_id", "amount"],
            history=store,
        )
        assert result.status == CheckStatus.PASSED
    finally:
        store.close()


def test_fails_on_added_column(tmp_path: Path):
    store = HistoryStore(path=tmp_path / "h.db")
    store.connect()
    try:
        fp = fingerprint(["order_id", "amount"])
        store.record("Revenue", value_sum=None, row_count=None, schema_fingerprint=fp)
        result = check_schema_drift(
            "Revenue",
            current_columns=["order_id", "amount", "new_col"],
            history=store,
        )
        assert result.status == CheckStatus.FAILED
        assert "new_col" in result.message
    finally:
        store.close()


def test_fails_on_removed_column(tmp_path: Path):
    store = HistoryStore(path=tmp_path / "h.db")
    store.connect()
    try:
        fp = fingerprint(["order_id", "amount", "status"])
        store.record("Revenue", value_sum=None, row_count=None, schema_fingerprint=fp)
        result = check_schema_drift(
            "Revenue",
            current_columns=["order_id", "amount"],
            history=store,
        )
        assert result.status == CheckStatus.FAILED
        assert "status" in result.message
    finally:
        store.close()


def test_fails_on_renamed_column(tmp_path: Path):
    store = HistoryStore(path=tmp_path / "h.db")
    store.connect()
    try:
        fp = fingerprint(["order_id", "amount", "status"])
        store.record("Revenue", value_sum=None, row_count=None, schema_fingerprint=fp)
        result = check_schema_drift(
            "Revenue",
            current_columns=["order_id", "amount", "state"],  # status → state
            history=store,
        )
        assert result.status == CheckStatus.FAILED
        assert "+state" in result.message
        assert "-status" in result.message
    finally:
        store.close()
