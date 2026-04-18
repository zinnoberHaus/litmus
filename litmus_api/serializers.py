from __future__ import annotations

from dataclasses import asdict
from typing import Any

from litmus.spec.metric_spec import MetricSpec


def spec_to_dict(spec: MetricSpec) -> dict[str, Any]:
    data = asdict(spec)
    data.pop("raw_text", None)
    return data


def slugify(name: str) -> str:
    import re

    slug = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip()).strip("_").lower()
    return slug or "metric"
