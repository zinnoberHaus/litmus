"""Core dataclasses representing parsed metric specifications."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FreshnessRule:
    max_hours: float


@dataclass
class NullRule:
    column: str
    max_percentage: float  # 0.0 to 100.0


@dataclass
class VolumeRule:
    table: str | None  # None means primary source
    max_drop_percentage: float
    period: str  # "day" | "week" | "month"


@dataclass
class RangeRule:
    min_value: float
    max_value: float


@dataclass
class ChangeRule:
    max_change_percentage: float
    period: str  # "day" | "week" | "month"


@dataclass
class DuplicateRule:
    column: str
    max_percentage: float  # 0.0 to 100.0


@dataclass
class SchemaDriftRule:
    """Stateful — compares current column list against the last recorded one."""


@dataclass
class DistributionShiftRule:
    column: str
    max_change_percentage: float
    period: str  # "day" | "week" | "month" | "quarter" | "year"


@dataclass
class TrustSpec:
    freshness: FreshnessRule | None = None
    null_rules: list[NullRule] = field(default_factory=list)
    volume_rules: list[VolumeRule] = field(default_factory=list)
    range_rules: list[RangeRule] = field(default_factory=list)
    change_rules: list[ChangeRule] = field(default_factory=list)
    duplicate_rules: list[DuplicateRule] = field(default_factory=list)
    schema_drift: SchemaDriftRule | None = None
    distribution_shift_rules: list[DistributionShiftRule] = field(default_factory=list)

    @property
    def total_checks(self) -> int:
        count = 0
        if self.freshness:
            count += 1
        count += len(self.null_rules)
        count += len(self.volume_rules)
        count += len(self.range_rules)
        count += len(self.change_rules)
        count += len(self.duplicate_rules)
        if self.schema_drift is not None:
            count += 1
        count += len(self.distribution_shift_rules)
        return count


@dataclass
class MetricSpec:
    name: str
    description: str | None = None
    owner: str | None = None
    tags: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    conditions: list[str] = field(default_factory=list)
    calculations: list[str] = field(default_factory=list)
    result_name: str | None = None
    trust: TrustSpec | None = None
    raw_text: str | None = None
