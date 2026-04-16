"""AST node definitions for .metric file parsing."""

from dataclasses import dataclass, field


@dataclass
class HeaderNode:
    name: str
    description: str | None = None
    owner: str | None = None
    tags: list[str] = field(default_factory=list)


@dataclass
class SourceNode:
    tables: list[str] = field(default_factory=list)


@dataclass
class ConditionNode:
    text: str
    line: int | None = None


@dataclass
class GivenBlock:
    conditions: list[ConditionNode] = field(default_factory=list)


@dataclass
class OperationNode:
    text: str
    line: int | None = None


@dataclass
class WhenBlock:
    operations: list[OperationNode] = field(default_factory=list)


@dataclass
class ResultNode:
    name: str


@dataclass
class FreshnessRuleNode:
    value: float
    unit: str  # "hours" | "minutes" | "days"

    @property
    def max_hours(self) -> float:
        if self.unit == "minutes":
            return self.value / 60
        if self.unit == "days":
            return self.value * 24
        return self.value


@dataclass
class NullRuleNode:
    column: str
    max_percentage: float


@dataclass
class VolumeRuleNode:
    table: str | None
    max_drop_percentage: float
    period: str  # "day" | "week" | "month"


@dataclass
class RangeRuleNode:
    min_value: float
    max_value: float


@dataclass
class ChangeRuleNode:
    max_change_percentage: float
    period: str  # "day" | "week" | "month"


@dataclass
class DuplicateRuleNode:
    column: str
    max_percentage: float


@dataclass
class SchemaDriftRuleNode:
    pass


@dataclass
class DistributionShiftRuleNode:
    column: str
    max_change_percentage: float
    period: str  # "day" | "week" | "month" | "quarter" | "year"


@dataclass
class TrustBlock:
    freshness: FreshnessRuleNode | None = None
    null_rules: list[NullRuleNode] = field(default_factory=list)
    volume_rules: list[VolumeRuleNode] = field(default_factory=list)
    range_rules: list[RangeRuleNode] = field(default_factory=list)
    change_rules: list[ChangeRuleNode] = field(default_factory=list)
    duplicate_rules: list[DuplicateRuleNode] = field(default_factory=list)
    schema_drift: SchemaDriftRuleNode | None = None
    distribution_shift_rules: list[DistributionShiftRuleNode] = field(default_factory=list)


@dataclass
class MetricFileAST:
    header: HeaderNode
    source: SourceNode
    given_block: GivenBlock
    when_block: WhenBlock
    result: ResultNode
    trust: TrustBlock | None = None
