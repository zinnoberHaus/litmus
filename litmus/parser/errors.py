"""Parser error handling with friendly, actionable error messages."""


class LitmusParseError(Exception):
    """Base error for all parsing failures."""

    def __init__(self, message: str, line: int | None = None, context: str | None = None):
        self.line = line
        self.context = context
        parts = []
        if line is not None:
            parts.append(f"Line {line}")
        parts.append(message)
        if context:
            parts.append(f"\n  Found: {context}")
        super().__init__(" — ".join(parts) if line else message)


class MissingHeaderError(LitmusParseError):
    """The .metric file is missing the required Metric: header."""

    def __init__(self, line: int | None = None):
        super().__init__(
            'Every .metric file must start with "Metric: <name>".',
            line=line,
        )


class MissingSectionError(LitmusParseError):
    """A required section is missing from the .metric file."""

    def __init__(self, section: str, line: int | None = None):
        super().__init__(
            f'Missing required section: "{section}". '
            f"Check the spec language reference for the expected format.",
            line=line,
        )


class InvalidTrustRuleError(LitmusParseError):
    """A trust rule could not be parsed."""

    def __init__(self, rule_text: str, line: int | None = None):
        super().__init__(
            "Could not parse trust rule. Expected one of:\n"
            '  Freshness must be less than <duration>\n'
            '  Null rate on <column> must be [less than] <percentage>\n'
            '  Row count [of <table>] must not drop more than <percentage> <period>\n'
            '  Value must be between <min> and <max>\n'
            '  Value must not change more than <percentage> <period>',
            line=line,
            context=rule_text.strip(),
        )


class UnexpectedTokenError(LitmusParseError):
    """An unexpected token was encountered during parsing."""

    def __init__(self, expected: str, got: str, line: int | None = None):
        super().__init__(
            f'Expected {expected}, but found "{got}".',
            line=line,
        )
