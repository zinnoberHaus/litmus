"""BI-tool connectors.

Only the abstract types are imported eagerly. Concrete connectors are lazy-
imported inside :func:`get_connector` so installing ``litmus-data[server]``
without the ``[bi]`` extras doesn't trip on a missing ``looker-sdk`` or
``tableauserverclient`` at import time.
"""

from __future__ import annotations

from litmus_api.bi.base import BaseBIConnector, BIResult

__all__ = ["BaseBIConnector", "BIResult", "get_connector", "SUPPORTED_SOURCES"]

SUPPORTED_SOURCES = ("looker", "tableau")


def get_connector(source: str) -> BaseBIConnector:
    """Factory: map a ``source`` string to a concrete connector instance.

    Raises ``ValueError`` for unknown sources so the API route can turn that
    into a 422 without an import error. Concrete classes are lazy-imported
    here — a Litmus server running without the ``[bi]`` extras still boots,
    it just fails the first time someone actually tries to reconcile.
    """
    normalized = source.lower().strip()
    if normalized == "looker":
        from litmus_api.bi.looker import LookerConnector

        return LookerConnector()
    if normalized == "tableau":
        from litmus_api.bi.tableau import TableauConnector

        return TableauConnector()
    raise ValueError(
        f"Unknown BI source {source!r} — supported: {', '.join(SUPPORTED_SOURCES)}"
    )
