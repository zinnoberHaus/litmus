"""Abstract base class for BI-tool connectors.

Every BI integration (Looker, Tableau, …) implements :class:`BaseBIConnector`
and exposes a single method: ``fetch_metric_value(identifier)`` returning a
:class:`BIResult`. The reconciliation job treats every connector identically —
dispatching is handled by :func:`litmus_api.bi.get_connector`, and warehouse
specifics must never leak past the ``BIResult`` boundary.

Identifier formats are **per-connector** (see each subclass docstring). Keeping
them as opaque strings lets us add new BI tools without reshaping ``BIMapping``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class BIResult:
    """A single metric value pulled from a BI tool.

    ``source`` is the BI tool identifier (``"looker"`` / ``"tableau"``) — it's
    stored back on the ``Reconciliation`` row verbatim. ``raw_metadata`` is a
    free-form dict for debugging; reconciliation logic only depends on
    ``value``.
    """

    source: str
    value: float
    recorded_at: datetime
    raw_metadata: dict[str, Any] = field(default_factory=dict)


class BaseBIConnector(ABC):
    """ABC every BI connector must implement.

    Instances are cheap to construct — auth happens lazily inside
    :meth:`fetch_metric_value` so a missing env var only bites when you
    actually try to reconcile a metric that uses that source.
    """

    source: str = ""

    @abstractmethod
    def fetch_metric_value(self, identifier: str) -> BIResult:
        """Resolve ``identifier`` to the current metric value in the BI tool.

        Implementations should raise a plain ``RuntimeError`` (or a narrower
        subclass) when the fetch fails — the reconciliation job catches every
        exception and records a ``status="fail"`` row, so never swallow errors
        inside the connector.
        """
        raise NotImplementedError
