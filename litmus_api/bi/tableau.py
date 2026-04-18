"""Tableau BI connector.

Uses ``tableauserverclient`` (TSC) with Personal Access Token auth — gated
behind the ``[bi]`` extras. PAT is preferred over username/password because it
can be scoped and rotated without touching a user account.

Identifier format
-----------------
``"<workbook_id>/<view_id>/<field_name>"``

Example: ``"abc-123/xyz-789/SUM(Sales)"``. We resolve the view by its LUID,
pull its summary data, and extract ``field_name`` from the first row. The
field name must match what Tableau emits in the CSV (typically the column
alias shown on the worksheet — e.g. ``"SUM(Sales)"``).
"""

from __future__ import annotations

import csv
import io
import os
from datetime import datetime, timezone
from typing import Any

from litmus_api.bi.base import BaseBIConnector, BIResult


class TableauConnector(BaseBIConnector):
    """Thin wrapper around ``tableauserverclient`` that returns a :class:`BIResult`.

    Environment variables (all required):

    - ``LITMUS_TABLEAU_SERVER_URL`` — e.g. ``https://10ax.online.tableau.com``
    - ``LITMUS_TABLEAU_SITE_ID`` — blank string is valid for the default site
    - ``LITMUS_TABLEAU_PAT_NAME``
    - ``LITMUS_TABLEAU_PAT_VALUE``
    """

    source = "tableau"

    def __init__(self) -> None:
        self._server: Any = None

    def _init_server(self) -> Any:
        if self._server is not None:
            return self._server

        server_url = os.environ.get("LITMUS_TABLEAU_SERVER_URL")
        # site_id is allowed to be empty (default site) — only treat None as missing.
        site_id = os.environ.get("LITMUS_TABLEAU_SITE_ID")
        pat_name = os.environ.get("LITMUS_TABLEAU_PAT_NAME")
        pat_value = os.environ.get("LITMUS_TABLEAU_PAT_VALUE")
        missing = [
            name
            for name, val in (
                ("LITMUS_TABLEAU_SERVER_URL", server_url),
                ("LITMUS_TABLEAU_SITE_ID", site_id),
                ("LITMUS_TABLEAU_PAT_NAME", pat_name),
                ("LITMUS_TABLEAU_PAT_VALUE", pat_value),
            )
            if val is None
        ]
        if missing:
            raise RuntimeError(
                f"Tableau connector missing env vars: {', '.join(missing)}"
            )

        import tableauserverclient as tsc  # type: ignore[import-not-found]

        auth = tsc.PersonalAccessTokenAuth(pat_name, pat_value, site_id or "")
        server = tsc.Server(server_url, use_server_version=True)
        server.auth.sign_in(auth)
        self._server = server
        return server

    def fetch_metric_value(self, identifier: str) -> BIResult:
        """Look up a Tableau view and extract a single field value.

        ``identifier`` format: ``"<workbook_id>/<view_id>/<field_name>"``.
        We intentionally round-trip through the view summary CSV rather than
        Tableau's experimental VizQL Data Service — CSV export is GA on every
        Tableau Server / Cloud deployment we expect OSS users to run against.
        """
        parts = identifier.split("/", 2)
        if len(parts) != 3:
            raise RuntimeError(
                "Tableau identifier must be 'workbook_id/view_id/field_name' "
                f"— got {identifier!r}"
            )
        workbook_id, view_id, field_name = parts

        server = self._init_server()

        view = server.views.get_by_id(view_id)
        if view is None:
            raise RuntimeError(f"Tableau view {view_id!r} not found")
        if workbook_id and getattr(view, "workbook_id", None) not in (None, workbook_id):
            raise RuntimeError(
                f"Tableau view {view_id!r} belongs to workbook "
                f"{view.workbook_id!r}, not {workbook_id!r}"
            )

        server.views.populate_csv(view)
        # populate_csv stacks byte chunks onto ``view.csv``; join + decode.
        raw = b"".join(view.csv).decode("utf-8-sig")
        value = _extract_scalar(raw, field_name)
        return BIResult(
            source=self.source,
            value=float(value),
            recorded_at=datetime.now(timezone.utc),
            raw_metadata={
                "workbook_id": workbook_id,
                "view_id": view_id,
                "field": field_name,
            },
        )


def _extract_scalar(csv_text: str, field: str) -> float:
    """Pull ``field`` from the first row of a Tableau view CSV export."""
    reader = csv.DictReader(io.StringIO(csv_text))
    for row in reader:
        if field not in row:
            raise RuntimeError(
                f"Tableau CSV missing field {field!r} — got columns {list(row.keys())}"
            )
        cleaned = (row[field] or "").replace(",", "").replace("$", "").strip()
        if not cleaned:
            raise RuntimeError(f"Tableau CSV field {field!r} is empty")
        try:
            return float(cleaned)
        except ValueError as exc:
            raise RuntimeError(
                f"Tableau CSV field {field!r} is not numeric: {row[field]!r}"
            ) from exc
    raise RuntimeError("Tableau CSV has no data rows")
