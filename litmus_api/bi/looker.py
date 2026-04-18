"""Looker BI connector.

Uses the official ``looker-sdk`` (gated behind the ``[bi]`` extras). The SDK
reads auth from either env vars or a ``looker.ini`` file — we pass the env
values in programmatically via an in-memory ``ApiSettings`` so no file is
needed on disk.

Identifier format
-----------------
``"<lookml_model>::<view>.<measure>"``

Example: ``"ecommerce::orders.total_revenue"`` runs a Looker inline query
against the ``ecommerce`` LookML model, pulling the ``total_revenue`` measure
off the ``orders`` view. One row, one value — the reconciliation job only
ever consumes a scalar.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from litmus_api.bi.base import BaseBIConnector, BIResult


class LookerConnector(BaseBIConnector):
    """Thin wrapper around ``looker-sdk`` that returns a :class:`BIResult`.

    Environment variables (all required):

    - ``LITMUS_LOOKER_BASE_URL`` — e.g. ``https://mycorp.looker.com``
    - ``LITMUS_LOOKER_CLIENT_ID``
    - ``LITMUS_LOOKER_CLIENT_SECRET``
    """

    source = "looker"

    def __init__(self) -> None:
        self._sdk: Any = None  # Lazy — only init'd on first fetch.

    def _init_sdk(self) -> Any:
        if self._sdk is not None:
            return self._sdk

        base_url = os.environ.get("LITMUS_LOOKER_BASE_URL")
        client_id = os.environ.get("LITMUS_LOOKER_CLIENT_ID")
        client_secret = os.environ.get("LITMUS_LOOKER_CLIENT_SECRET")
        missing = [
            name
            for name, val in (
                ("LITMUS_LOOKER_BASE_URL", base_url),
                ("LITMUS_LOOKER_CLIENT_ID", client_id),
                ("LITMUS_LOOKER_CLIENT_SECRET", client_secret),
            )
            if not val
        ]
        if missing:
            raise RuntimeError(
                f"Looker connector missing env vars: {', '.join(missing)}"
            )

        # Push creds into env vars under the names the SDK reads — cheapest
        # way to stay compatible with its config loader without writing an
        # ini file to disk.
        os.environ["LOOKERSDK_BASE_URL"] = base_url or ""
        os.environ["LOOKERSDK_CLIENT_ID"] = client_id or ""
        os.environ["LOOKERSDK_CLIENT_SECRET"] = client_secret or ""
        os.environ.setdefault("LOOKERSDK_API_VERSION", "4.0")

        import looker_sdk  # type: ignore[import-not-found]

        self._sdk = looker_sdk.init40()
        return self._sdk

    def fetch_metric_value(self, identifier: str) -> BIResult:
        """Run an inline query against Looker for a single measure.

        ``identifier`` format: ``"<model>::<view>.<measure>"`` — e.g.
        ``"ecommerce::orders.total_revenue"``. We build a 1-field inline query
        and expect Looker to return exactly one row.
        """
        try:
            model, field = identifier.split("::", 1)
        except ValueError as exc:
            raise RuntimeError(
                f"Looker identifier must be '<model>::<view.measure>' — got {identifier!r}"
            ) from exc

        if "." not in field:
            raise RuntimeError(
                f"Looker field must be 'view.measure' — got {field!r}"
            )

        sdk = self._init_sdk()

        from looker_sdk import models40  # type: ignore[import-not-found]

        body = models40.WriteQuery(model=model, view=field.split(".", 1)[0], fields=[field])
        result = sdk.run_inline_query(result_format="json", body=body)

        value = _extract_scalar(result, field)
        return BIResult(
            source=self.source,
            value=float(value),
            recorded_at=datetime.now(timezone.utc),
            raw_metadata={"model": model, "field": field},
        )


def _extract_scalar(raw: Any, field: str) -> float:
    """Parse a Looker JSON response into a single float.

    ``run_inline_query`` returns a JSON string; we take the first row's value
    for ``field``. If the response is empty or malformed we raise RuntimeError
    so the reconciliation job records a ``fail`` row with a clear message.
    """
    import json

    rows: list[dict[str, Any]]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Looker returned non-JSON: {raw[:120]!r}") from exc
        if not isinstance(parsed, list):
            raise RuntimeError(f"Looker JSON was not a list: {type(parsed).__name__}")
        rows = parsed
    elif isinstance(raw, list):
        rows = raw
    else:
        raise RuntimeError(f"Unexpected Looker response type: {type(raw).__name__}")

    if not rows:
        raise RuntimeError("Looker query returned no rows")

    first = rows[0]
    if field not in first:
        raise RuntimeError(
            f"Looker response missing field {field!r} — got keys {list(first.keys())}"
        )
    return float(first[field])
