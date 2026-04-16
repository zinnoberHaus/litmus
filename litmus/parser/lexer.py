"""Tokenize .metric files into structured lines for the parser."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum, auto


class TokenType(Enum):
    METRIC = auto()
    DESCRIPTION = auto()
    OWNER = auto()
    TAGS = auto()
    SOURCE = auto()
    GIVEN = auto()
    AND = auto()
    WHEN = auto()
    THEN = auto()
    RESULT = auto()
    TRUST_HEADER = auto()
    TRUST_RULE = auto()
    BLANK = auto()
    COMMENT = auto()


@dataclass
class Token:
    type: TokenType
    value: str
    line: int

    def __repr__(self) -> str:
        return f"Token({self.type.name}, {self.value!r}, line={self.line})"


# Patterns ordered by specificity
_LINE_PATTERNS: list[tuple[re.Pattern[str], TokenType]] = [
    (re.compile(r"^Metric:\s*(.+)$", re.IGNORECASE), TokenType.METRIC),
    (re.compile(r"^Description:\s*(.+)$", re.IGNORECASE), TokenType.DESCRIPTION),
    (re.compile(r"^Owner:\s*(.+)$", re.IGNORECASE), TokenType.OWNER),
    (re.compile(r"^Tags:\s*(.+)$", re.IGNORECASE), TokenType.TAGS),
    (re.compile(r"^Source:\s*(.+)$", re.IGNORECASE), TokenType.SOURCE),
    (re.compile(r"^Given\s+(.+)$", re.IGNORECASE), TokenType.GIVEN),
    (re.compile(r"^When\s+we\s+calculate\s*$", re.IGNORECASE), TokenType.WHEN),
    (re.compile(r"^\s+Then\s+(.+)$", re.IGNORECASE), TokenType.THEN),
    (re.compile(r"^\s+And\s+(.+)$", re.IGNORECASE), TokenType.AND),
    (re.compile(r"^And\s+(.+)$", re.IGNORECASE), TokenType.AND),
    (re.compile(r"^Then\s+(.+)$", re.IGNORECASE), TokenType.THEN),
    (re.compile(r'^The\s+result\s+is\s+"([^"]+)"\s*$', re.IGNORECASE), TokenType.RESULT),
    (re.compile(r"^Trust:\s*$", re.IGNORECASE), TokenType.TRUST_HEADER),
    (re.compile(r"^\s{2,}(.+)$"), TokenType.TRUST_RULE),
]


def tokenize(text: str) -> list[Token]:
    """Tokenize a .metric file into a list of Tokens.

    Blank lines and comment lines (starting with #) are included but
    can be filtered out by the parser.
    """
    tokens: list[Token] = []

    for line_num, raw_line in enumerate(text.splitlines(), start=1):
        stripped = raw_line.rstrip()

        if not stripped:
            tokens.append(Token(TokenType.BLANK, "", line_num))
            continue

        if stripped.lstrip().startswith("#"):
            tokens.append(Token(TokenType.COMMENT, stripped, line_num))
            continue

        matched = False
        for pattern, token_type in _LINE_PATTERNS:
            m = pattern.match(stripped)
            if m:
                value = m.group(1) if m.lastindex else stripped
                tokens.append(Token(token_type, value.strip(), line_num))
                matched = True
                break

        if not matched:
            # Indented lines inside the trust block that didn't match the
            # TRUST_RULE pattern (e.g. single-space indent) — try treating
            # as trust rule if we are past a TRUST_HEADER.
            in_trust = any(t.type == TokenType.TRUST_HEADER for t in tokens)
            if in_trust and stripped.startswith(" "):
                tokens.append(Token(TokenType.TRUST_RULE, stripped.strip(), line_num))
            else:
                # Treat as continuation of previous context — AND without keyword
                tokens.append(Token(TokenType.AND, stripped.strip(), line_num))

    return tokens


def filter_tokens(tokens: list[Token]) -> list[Token]:
    """Remove blanks and comments, returning only meaningful tokens."""
    return [t for t in tokens if t.type not in (TokenType.BLANK, TokenType.COMMENT)]
