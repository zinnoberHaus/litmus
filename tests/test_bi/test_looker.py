"""Looker connector tests.

We never hit a real Looker instance — the SDK is mocked end-to-end. The
contract we lock in:

- ``init40`` is called when (and only when) ``fetch_metric_value`` is invoked.
- The identifier parses into ``<model>::<view>.<measure>``.
- The response maps to a :class:`BIResult` with a float value and the
  ``looker`` source.
- Missing env vars fail loudly, not silently.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import pytest

from litmus_api.bi.base import BIResult


@pytest.fixture()
def looker_env(monkeypatch) -> None:
    monkeypatch.setenv("LITMUS_LOOKER_BASE_URL", "https://demo.looker.com")
    monkeypatch.setenv("LITMUS_LOOKER_CLIENT_ID", "client-id")
    monkeypatch.setenv("LITMUS_LOOKER_CLIENT_SECRET", "client-secret")


def _install_fake_looker_sdk(run_inline_result: str = '[{"orders.total_revenue": 123.45}]'):
    """Register a stub ``looker_sdk`` module so ``import looker_sdk`` works
    inside the connector without the real SDK installed.

    Returns the mock ``sdk`` instance so tests can assert on it.
    """
    fake = types.ModuleType("looker_sdk")
    sdk_instance = MagicMock()
    sdk_instance.run_inline_query.return_value = run_inline_result
    fake.init40 = MagicMock(return_value=sdk_instance)  # type: ignore[attr-defined]

    models40 = types.ModuleType("looker_sdk.models40")
    models40.WriteQuery = MagicMock()  # type: ignore[attr-defined]

    sys.modules["looker_sdk"] = fake
    sys.modules["looker_sdk.models40"] = models40
    return sdk_instance


def test_fetch_metric_value_returns_biresult(looker_env) -> None:
    sdk_instance = _install_fake_looker_sdk('[{"orders.total_revenue": 4200.0}]')

    from litmus_api.bi.looker import LookerConnector

    connector = LookerConnector()
    result = connector.fetch_metric_value("ecommerce::orders.total_revenue")

    assert isinstance(result, BIResult)
    assert result.source == "looker"
    assert result.value == pytest.approx(4200.0)
    assert result.raw_metadata == {
        "model": "ecommerce",
        "field": "orders.total_revenue",
    }
    # The SDK was actually called — not just the connector pretending to work.
    sdk_instance.run_inline_query.assert_called_once()
    # And WriteQuery was instantiated with the split-out model/view/fields.
    from looker_sdk import models40  # type: ignore[import-not-found]

    models40.WriteQuery.assert_called_once()
    call_kwargs = models40.WriteQuery.call_args.kwargs
    assert call_kwargs["model"] == "ecommerce"
    assert call_kwargs["view"] == "orders"
    assert call_kwargs["fields"] == ["orders.total_revenue"]


def test_missing_env_vars_raise(monkeypatch) -> None:
    # Wipe the env so init_sdk can see the gap.
    for var in (
        "LITMUS_LOOKER_BASE_URL",
        "LITMUS_LOOKER_CLIENT_ID",
        "LITMUS_LOOKER_CLIENT_SECRET",
    ):
        monkeypatch.delenv(var, raising=False)

    from litmus_api.bi.looker import LookerConnector

    connector = LookerConnector()
    with pytest.raises(RuntimeError, match="missing env vars"):
        connector.fetch_metric_value("model::view.measure")


def test_malformed_identifier_raises(looker_env) -> None:
    _install_fake_looker_sdk()
    from litmus_api.bi.looker import LookerConnector

    connector = LookerConnector()
    with pytest.raises(RuntimeError, match="<model>::<view.measure>"):
        connector.fetch_metric_value("no-separator")


def test_empty_rows_raises(looker_env) -> None:
    _install_fake_looker_sdk("[]")
    from litmus_api.bi.looker import LookerConnector

    connector = LookerConnector()
    with pytest.raises(RuntimeError, match="no rows"):
        connector.fetch_metric_value("ecommerce::orders.total_revenue")


def test_init_not_called_when_fetch_not_called(looker_env) -> None:
    """Constructing the connector must not touch the SDK — auth is lazy.

    This matters because FastAPI instantiates connectors inside a request
    handler, and we don't want a route that doesn't need BI auth to 500
    because Looker happens to be misconfigured.
    """
    # Don't install the fake module — if the connector touched the SDK on
    # construction, the import below would fail.
    with patch.dict(sys.modules, {"looker_sdk": None}):
        # Even with the import pre-broken, constructing the connector works.
        from litmus_api.bi.looker import LookerConnector

        LookerConnector()  # should not raise
