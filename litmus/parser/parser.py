"""Parse tokenized .metric files into an AST, then lower to MetricSpec."""

from __future__ import annotations

import re
from pathlib import Path

from litmus.parser.ast_nodes import (
    ChangeRuleNode,
    ConditionNode,
    DistributionShiftRuleNode,
    DuplicateRuleNode,
    FreshnessRuleNode,
    GivenBlock,
    HeaderNode,
    MetricFileAST,
    NullRuleNode,
    OperationNode,
    RangeRuleNode,
    ResultNode,
    SchemaDriftRuleNode,
    SourceNode,
    TrustBlock,
    VolumeRuleNode,
    WhenBlock,
)
from litmus.parser.errors import (
    InvalidTrustRuleError,
    MissingHeaderError,
    MissingSectionError,
    UnexpectedTokenError,
)
from litmus.parser.lexer import Token, TokenType, filter_tokens, tokenize
from litmus.spec.metric_spec import (
    ChangeRule,
    DistributionShiftRule,
    DuplicateRule,
    FreshnessRule,
    MetricSpec,
    NullRule,
    RangeRule,
    SchemaDriftRule,
    TrustSpec,
    VolumeRule,
)


class _Parser:
    """Recursive-descent parser for .metric file tokens."""

    def __init__(self, tokens: list[Token], raw_text: str):
        self.tokens = tokens
        self.raw_text = raw_text
        self.pos = 0

    # ── helpers ──────────────────────────────────────────────────────

    def _peek(self) -> Token | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def _advance(self) -> Token:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def _expect(self, *types: TokenType) -> Token:
        tok = self._peek()
        if tok is None:
            expected = " or ".join(t.name for t in types)
            raise MissingSectionError(expected)
        if tok.type not in types:
            expected = " or ".join(t.name for t in types)
            raise UnexpectedTokenError(expected, tok.value, tok.line)
        return self._advance()

    def _at(self, *types: TokenType) -> bool:
        tok = self._peek()
        return tok is not None and tok.type in types

    # ── grammar rules ───────────────────────────────────────────────

    def parse(self) -> MetricFileAST:
        header = self._parse_header()
        source = self._parse_source()
        given = self._parse_given()
        when = self._parse_when()
        result = self._parse_result()
        trust = self._parse_trust() if self._at(TokenType.TRUST_HEADER) else None
        return MetricFileAST(header, source, given, when, result, trust)

    def _parse_header(self) -> HeaderNode:
        tok = self._peek()
        if tok is None or tok.type != TokenType.METRIC:
            raise MissingHeaderError(tok.line if tok else 1)
        name_tok = self._advance()
        desc = None
        owner = None
        tags: list[str] = []

        while self._at(TokenType.DESCRIPTION, TokenType.OWNER, TokenType.TAGS):
            tok = self._advance()
            if tok.type == TokenType.DESCRIPTION:
                desc = tok.value
            elif tok.type == TokenType.OWNER:
                owner = tok.value
            elif tok.type == TokenType.TAGS:
                tags = [t.strip() for t in tok.value.split(",")]

        return HeaderNode(name=name_tok.value, description=desc, owner=owner, tags=tags)

    def _parse_source(self) -> SourceNode:
        tok = self._expect(TokenType.SOURCE)
        tables = [t.strip() for t in tok.value.split(",")]
        return SourceNode(tables=tables)

    def _parse_given(self) -> GivenBlock:
        tok = self._expect(TokenType.GIVEN)
        conditions = [ConditionNode(text=tok.value, line=tok.line)]
        while self._at(TokenType.AND):
            and_tok = self._advance()
            conditions.append(ConditionNode(text=and_tok.value, line=and_tok.line))
        return GivenBlock(conditions=conditions)

    def _parse_when(self) -> WhenBlock:
        self._expect(TokenType.WHEN)
        operations: list[OperationNode] = []
        # First operation after "When we calculate" starts with Then
        if self._at(TokenType.THEN):
            tok = self._advance()
            operations.append(OperationNode(text=tok.value, line=tok.line))
        while self._at(TokenType.AND):
            tok = self._advance()
            operations.append(OperationNode(text=tok.value, line=tok.line))
        return WhenBlock(operations=operations)

    def _parse_result(self) -> ResultNode:
        tok = self._expect(TokenType.RESULT)
        return ResultNode(name=tok.value)

    def _parse_trust(self) -> TrustBlock:
        self._advance()  # consume TRUST_HEADER
        block = TrustBlock()
        while self._at(TokenType.TRUST_RULE):
            tok = self._advance()
            self._parse_trust_rule(tok.value, tok.line, block)
        return block

    # ── trust rule sub-parsers ──────────────────────────────────────

    _RE_FRESHNESS = re.compile(
        r"^Freshness\s+must\s+be\s+less\s+than\s+(\d+(?:\.\d+)?)\s*(hours?|minutes?|days?)\s*$",
        re.IGNORECASE,
    )
    _RE_NULL = re.compile(
        r"^Null\s+rate\s+on\s+(\w+)\s+must\s+be\s+(?:less\s+than\s+)?(\d+(?:\.\d+)?)%?\s*$",
        re.IGNORECASE,
    )
    _RE_VOLUME = re.compile(
        r"^Row\s+count\s*(?:of\s+(\w+))?\s*must\s+not\s+drop\s+more\s+than\s+"
        r"(\d+(?:\.\d+)?)%?\s+(day\s+over\s+day|week\s+over\s+week|month\s+over\s+month)\s*$",
        re.IGNORECASE,
    )
    _RE_RANGE = re.compile(
        r"^Value\s+must\s+be\s+between\s+([\d.,]+)%?\s+and\s+([\d.,]+)%?\s*$",
        re.IGNORECASE,
    )
    _RE_CHANGE = re.compile(
        r"^Value\s+must\s+not\s+change\s+more\s+than\s+(\d+(?:\.\d+)?)%?\s+"
        r"(day\s+over\s+day|week\s+over\s+week|month\s+over\s+month)\s*$",
        re.IGNORECASE,
    )
    _RE_DUPLICATE = re.compile(
        r"^Duplicate\s+rate\s+on\s+(\w+)\s+must\s+be\s+(?:less\s+than\s+)?"
        r"(\d+(?:\.\d+)?)%?\s*$",
        re.IGNORECASE,
    )
    _RE_SCHEMA_DRIFT = re.compile(
        r"^Schema\s+must\s+not\s+(?:drift|change)\s*$",
        re.IGNORECASE,
    )
    _RE_DISTRIBUTION_SHIFT = re.compile(
        r"^Mean\s+of\s+(\w+)\s+must\s+not\s+(?:shift|change)\s+more\s+than\s+"
        r"(\d+(?:\.\d+)?)%?\s+"
        r"(day\s+over\s+day|week\s+over\s+week|month\s+over\s+month|"
        r"quarter\s+over\s+quarter|year\s+over\s+year)\s*$",
        re.IGNORECASE,
    )

    @staticmethod
    def _period_key(raw: str) -> str:
        """Normalize 'day over day' → 'day'."""
        return raw.strip().split()[0].lower()

    def _parse_trust_rule(self, text: str, line: int, block: TrustBlock) -> None:
        m = self._RE_FRESHNESS.match(text)
        if m:
            unit = m.group(2).lower().rstrip("s") + "s"  # normalize to plural
            block.freshness = FreshnessRuleNode(value=float(m.group(1)), unit=unit)
            return

        m = self._RE_NULL.match(text)
        if m:
            block.null_rules.append(
                NullRuleNode(column=m.group(1), max_percentage=float(m.group(2)))
            )
            return

        m = self._RE_VOLUME.match(text)
        if m:
            block.volume_rules.append(
                VolumeRuleNode(
                    table=m.group(1),
                    max_drop_percentage=float(m.group(2)),
                    period=self._period_key(m.group(3)),
                )
            )
            return

        m = self._RE_RANGE.match(text)
        if m:
            min_val = float(m.group(1).replace(",", ""))
            max_val = float(m.group(2).replace(",", ""))
            block.range_rules.append(RangeRuleNode(min_value=min_val, max_value=max_val))
            return

        m = self._RE_CHANGE.match(text)
        if m:
            block.change_rules.append(
                ChangeRuleNode(
                    max_change_percentage=float(m.group(1)),
                    period=self._period_key(m.group(2)),
                )
            )
            return

        m = self._RE_DUPLICATE.match(text)
        if m:
            block.duplicate_rules.append(
                DuplicateRuleNode(column=m.group(1), max_percentage=float(m.group(2)))
            )
            return

        m = self._RE_SCHEMA_DRIFT.match(text)
        if m:
            block.schema_drift = SchemaDriftRuleNode()
            return

        m = self._RE_DISTRIBUTION_SHIFT.match(text)
        if m:
            block.distribution_shift_rules.append(
                DistributionShiftRuleNode(
                    column=m.group(1),
                    max_change_percentage=float(m.group(2)),
                    period=self._period_key(m.group(3)),
                )
            )
            return

        raise InvalidTrustRuleError(text, line)


# ── AST → MetricSpec lowering ────────────────────────────────────────


def _lower_trust(block: TrustBlock | None) -> TrustSpec | None:
    if block is None:
        return None
    return TrustSpec(
        freshness=FreshnessRule(max_hours=block.freshness.max_hours) if block.freshness else None,
        null_rules=[
            NullRule(column=r.column, max_percentage=r.max_percentage)
            for r in block.null_rules
        ],
        volume_rules=[
            VolumeRule(table=r.table, max_drop_percentage=r.max_drop_percentage, period=r.period)
            for r in block.volume_rules
        ],
        range_rules=[
            RangeRule(min_value=r.min_value, max_value=r.max_value)
            for r in block.range_rules
        ],
        change_rules=[
            ChangeRule(max_change_percentage=r.max_change_percentage, period=r.period)
            for r in block.change_rules
        ],
        duplicate_rules=[
            DuplicateRule(column=r.column, max_percentage=r.max_percentage)
            for r in block.duplicate_rules
        ],
        schema_drift=SchemaDriftRule() if block.schema_drift is not None else None,
        distribution_shift_rules=[
            DistributionShiftRule(
                column=r.column,
                max_change_percentage=r.max_change_percentage,
                period=r.period,
            )
            for r in block.distribution_shift_rules
        ],
    )


def _lower(ast: MetricFileAST, raw_text: str) -> MetricSpec:
    return MetricSpec(
        name=ast.header.name,
        description=ast.header.description,
        owner=ast.header.owner,
        tags=ast.header.tags,
        sources=ast.source.tables,
        conditions=[c.text for c in ast.given_block.conditions],
        calculations=[o.text for o in ast.when_block.operations],
        result_name=ast.result.name,
        trust=_lower_trust(ast.trust),
        raw_text=raw_text,
    )


# ── public API ───────────────────────────────────────────────────────


def parse_metric_string(text: str) -> MetricSpec:
    """Parse a .metric format string and return a MetricSpec."""
    tokens = filter_tokens(tokenize(text))
    ast = _Parser(tokens, text).parse()
    return _lower(ast, text)


def parse_metric_file(path: str | Path) -> MetricSpec:
    """Parse a .metric file from disk and return a MetricSpec."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    try:
        return parse_metric_string(text)
    except Exception as exc:
        # Prefix file path for better error messages
        raise type(exc)(f"{path}: {exc}") from exc
