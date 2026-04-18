"""Tableau connector tests — SDK is stubbed out, never hits a real server."""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest

from litmus_api.bi.base import BIResult


@pytest.fixture()
def tableau_env(monkeypatch) -> None:
    monkeypatch.setenv("LITMUS_TABLEAU_SERVER_URL", "https://10ax.online.tableau.com")
    monkeypatch.setenv("LITMUS_TABLEAU_SITE_ID", "mysite")
    monkeypatch.setenv("LITMUS_TABLEAU_PAT_NAME", "litmus-pat")
    monkeypatch.setenv("LITMUS_TABLEAU_PAT_VALUE", "hunter2")


def _install_fake_tsc(csv_body: str = "SUM(Sales)\n4200.00\n", workbook_id: str = "wb-1"):
    """Register a stub ``tableauserverclient`` and return the Server mock."""
    fake = types.ModuleType("tableauserverclient")
    server_instance = MagicMock()

    # views.get_by_id returns a view with a ``csv`` attribute that
    # ``populate_csv`` populates. Mirror that in the mock.
    view = MagicMock()
    view.workbook_id = workbook_id
    view.csv = []

    def _populate(v):
        v.csv = [csv_body.encode("utf-8")]

    server_instance.views.get_by_id.return_value = view
    server_instance.views.populate_csv.side_effect = _populate

    fake.Server = MagicMock(return_value=server_instance)  # type: ignore[attr-defined]
    fake.PersonalAccessTokenAuth = MagicMock()  # type: ignore[attr-defined]

    sys.modules["tableauserverclient"] = fake
    return server_instance, view


def test_fetch_metric_value_returns_biresult(tableau_env) -> None:
    server, view = _install_fake_tsc(
        csv_body="SUM(Sales)\n4200.00\n", workbook_id="wb-1"
    )

    from litmus_api.bi.tableau import TableauConnector

    connector = TableauConnector()
    result = connector.fetch_metric_value("wb-1/view-abc/SUM(Sales)")

    assert isinstance(result, BIResult)
    assert result.source == "tableau"
    assert result.value == pytest.approx(4200.0)
    # The view/workbook/field lookup chain actually ran.
    server.auth.sign_in.assert_called_once()
    server.views.get_by_id.assert_called_once_with("view-abc")
    server.views.populate_csv.assert_called_once_with(view)


def test_fetch_handles_numeric_commas(tableau_env) -> None:
    """Tableau quotes values containing commas in its CSV export; once
    unquoted we still need to strip the ``,`` and ``$`` formatting so the
    value parses as a float rather than crashing on ``$4,200.50``.
    """
    _install_fake_tsc(csv_body='SUM(Sales)\n"$4,200.50"\n', workbook_id="wb-1")

    from litmus_api.bi.tableau import TableauConnector

    result = TableauConnector().fetch_metric_value("wb-1/view-abc/SUM(Sales)")
    assert result.value == pytest.approx(4200.5)


def test_workbook_mismatch_raises(tableau_env) -> None:
    _install_fake_tsc(workbook_id="wb-DIFFERENT")
    from litmus_api.bi.tableau import TableauConnector

    with pytest.raises(RuntimeError, match="belongs to workbook"):
        TableauConnector().fetch_metric_value("wb-1/view-abc/SUM(Sales)")


def test_malformed_identifier_raises(tableau_env) -> None:
    _install_fake_tsc()
    from litmus_api.bi.tableau import TableauConnector

    with pytest.raises(RuntimeError, match="workbook_id/view_id/field_name"):
        TableauConnector().fetch_metric_value("only-two/parts")


def test_missing_field_raises(tableau_env) -> None:
    _install_fake_tsc(csv_body="OtherField\n100\n")
    from litmus_api.bi.tableau import TableauConnector

    with pytest.raises(RuntimeError, match="missing field"):
        TableauConnector().fetch_metric_value("wb-1/view-abc/SUM(Sales)")


def test_missing_env_vars_raise(monkeypatch) -> None:
    for var in (
        "LITMUS_TABLEAU_SERVER_URL",
        "LITMUS_TABLEAU_SITE_ID",
        "LITMUS_TABLEAU_PAT_NAME",
        "LITMUS_TABLEAU_PAT_VALUE",
    ):
        monkeypatch.delenv(var, raising=False)

    from litmus_api.bi.tableau import TableauConnector

    with pytest.raises(RuntimeError, match="missing env vars"):
        TableauConnector().fetch_metric_value("wb-1/view-abc/SUM(Sales)")
