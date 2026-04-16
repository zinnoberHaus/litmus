"""Tests for litmus.parser.lexer — tokenization of .metric files."""

from __future__ import annotations

from textwrap import dedent

from litmus.parser.lexer import TokenType, filter_tokens, tokenize

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_METRIC = dedent("""\
    Metric: Test Revenue
    Description: Total revenue from completed orders
    Owner: data-team
    Tags: finance, revenue

    # This is a comment

    Source: orders

    Given all records from orders table
      And status is "completed"

    When we calculate
      Then sum the amount column

    The result is "Test Revenue"

    Trust:
      Freshness must be less than 24 hours
      Null rate on amount must be less than 5%
""")


# ---------------------------------------------------------------------------
# Token type tests
# ---------------------------------------------------------------------------


class TestTokenize:
    """Verify that tokenize produces the correct token types."""

    def test_tokenize_valid_metric_has_expected_types(self):
        tokens = tokenize(_VALID_METRIC)
        types = [t.type for t in tokens]

        assert TokenType.METRIC in types
        assert TokenType.DESCRIPTION in types
        assert TokenType.OWNER in types
        assert TokenType.TAGS in types
        assert TokenType.SOURCE in types
        assert TokenType.GIVEN in types
        assert TokenType.AND in types
        assert TokenType.WHEN in types
        assert TokenType.THEN in types
        assert TokenType.RESULT in types
        assert TokenType.TRUST_HEADER in types
        assert TokenType.TRUST_RULE in types

    def test_metric_token_extracts_name(self):
        tokens = tokenize("Metric: My Cool Metric")
        assert tokens[0].type == TokenType.METRIC
        assert tokens[0].value == "My Cool Metric"

    def test_source_token_extracts_table(self):
        tokens = tokenize("Source: orders")
        assert tokens[0].type == TokenType.SOURCE
        assert tokens[0].value == "orders"

    def test_given_token_extracts_condition(self):
        tokens = tokenize("Given all records from orders table")
        assert tokens[0].type == TokenType.GIVEN
        assert "all records from orders table" in tokens[0].value

    def test_result_token_extracts_name(self):
        tokens = tokenize('The result is "Total Revenue"')
        assert tokens[0].type == TokenType.RESULT
        assert tokens[0].value == "Total Revenue"

    def test_line_numbers_are_correct(self):
        tokens = tokenize(_VALID_METRIC)
        # First token on line 1
        assert tokens[0].line == 1
        # Every token tracks its line
        for tok in tokens:
            assert tok.line >= 1


class TestBlankTokens:
    """Blank lines become BLANK tokens."""

    def test_blank_lines_produce_blank_tokens(self):
        tokens = tokenize("Metric: Test\n\nSource: orders")
        blanks = [t for t in tokens if t.type == TokenType.BLANK]
        assert len(blanks) == 1
        assert blanks[0].value == ""

    def test_multiple_blank_lines(self):
        tokens = tokenize("Metric: Test\n\n\n\nSource: orders")
        blanks = [t for t in tokens if t.type == TokenType.BLANK]
        assert len(blanks) == 3


class TestCommentTokens:
    """Comment lines (starting with #) become COMMENT tokens."""

    def test_comment_line_produces_comment_token(self):
        tokens = tokenize("# This is a comment")
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.COMMENT
        assert "This is a comment" in tokens[0].value

    def test_indented_comment_still_matches(self):
        tokens = tokenize("  # indented comment")
        assert tokens[0].type == TokenType.COMMENT

    def test_comment_in_context(self):
        tokens = tokenize(_VALID_METRIC)
        comments = [t for t in tokens if t.type == TokenType.COMMENT]
        assert len(comments) >= 1
        assert "This is a comment" in comments[0].value


class TestFilterTokens:
    """filter_tokens removes BLANK and COMMENT tokens."""

    def test_filter_removes_blanks_and_comments(self):
        tokens = tokenize(_VALID_METRIC)
        filtered = filter_tokens(tokens)

        for tok in filtered:
            assert tok.type not in (TokenType.BLANK, TokenType.COMMENT)

    def test_filter_preserves_meaningful_tokens(self):
        tokens = tokenize(_VALID_METRIC)
        all_meaningful = [
            t for t in tokens if t.type not in (TokenType.BLANK, TokenType.COMMENT)
        ]
        filtered = filter_tokens(tokens)
        assert len(filtered) == len(all_meaningful)

    def test_filter_on_empty_list(self):
        assert filter_tokens([]) == []

    def test_filter_all_blanks(self):
        tokens = tokenize("\n\n\n")
        filtered = filter_tokens(tokens)
        assert filtered == []
