# `litmus/parser/` — `.metric` → `MetricSpec`

Turns a `.metric` file into a `MetricSpec` dataclass. Hand-rolled lexer + recursive-descent parser; no PLY, Lark, or other grammar library.

## Pipeline

```
.metric text
    │
    ▼  lexer.py  — line-oriented tokenizer (regex table)
list[Token]
    │
    ▼  parser.py — recursive-descent, enforces Header → Source → Given → When → Result → Trust?
MetricFileAST  (dataclasses in ast_nodes.py)
    │
    ▼  parser.py (lowering in parse_metric_*)
MetricSpec     (spec/metric_spec.py — the boundary between parsing and everything else)
```

Everything downstream of parsing consumes `MetricSpec` only. AST nodes never escape this package.

## Files

| File | Role |
|------|------|
| `lexer.py` | One regex per line type in `_LINE_PATTERNS`, **matched in order** (specific before general). Produces `Token(type, value, line)`. |
| `ast_nodes.py` | Dataclasses: `HeaderNode`, `SourceNode`, `GivenBlock`, `WhenBlock`, `ResultNode`, `TrustBlock` + per-rule nodes. |
| `parser.py` | `_Parser` class (recursive descent) + top-level `parse_metric_file` / `parse_metric_string`. |
| `errors.py` | Typed parse errors: `MissingHeaderError`, `MissingSectionError`, `UnexpectedTokenError`, `InvalidTrustRuleError`. |

## Adding a new syntax construct

Canonical checklist (owned by the **litmus-architect** agent):

1. Add a `TokenType` + regex in `lexer.py`. **Watch ordering** — a new broad pattern can shadow existing tokens.
2. Add an AST node in `ast_nodes.py`.
3. Wire parsing in `parser.py` — either a new section handler or a branch in `_parse_trust_rule`.
4. Mirror the shape in `../spec/metric_spec.py`; update `TrustSpec.total_checks` if applicable.
5. Add a fixture under `../tests/test_parser/test_fixtures/` and cases in `test_lexer.py` / `test_parser.py`.
6. Hand off: **litmus-inspector** implements runtime semantics; **litmus-advocate** updates `docs/spec-language.md`, `explain`, reporters, examples.

## Design rules

- Parser must have **zero runtime dependencies** — no DuckDB, no Click, no Rich. `import litmus.parser` should work in a minimal Python install.
- `from __future__ import annotations` everywhere; target 3.10+.
- Comments (`# …`) and blank lines are tokenized but filtered before parsing.
- Trust rules are data, not code — `TrustSpec` is declarative, evaluation lives in `litmus/checks/`.

## Testing

Use `sample_metric_text` and `sample_metric_file` fixtures from `tests/conftest.py`. Fixture `.metric` files live in `tests/test_parser/test_fixtures/`.
