# `litmus/reporters/` — Output formatters

Render `list[tuple[MetricSpec, CheckSuite]]` into a human- or machine-readable format. Every reporter takes the same input shape; the CLI picks one based on `--format` or the `reporting.format` config key.

## Formats

| Module | Output | Typical use |
|--------|--------|-------------|
| `console.py` | Rich-formatted terminal text | Interactive `litmus check` |
| `html_reporter.py` | Standalone HTML page | Share with stakeholders / CI artifact |
| `json_reporter.py` | JSON | Pipe into other tools / dashboards |
| `markdown_reporter.py` | Markdown | Slack, GitHub comments, docs |

## Public fields (JSON schema is a stable API)

Changes to these field names are **breaking** for external consumers of the JSON output. A major version bump is required.

### `CheckSuite`

- `metric_name: str`
- `results: list[CheckResult]`
- `passed / warnings / failed / errors / total: int` (computed)
- `trust_score: tuple[float, int]` — `(score, max)`. Warnings count as 0.5.
- `trust_score_display: str` — e.g. `"4.5/5"`.
- `health_indicator: str` — emoji (🔴 / 🟡 / 🟢).

### `CheckResult`

- `name: str` — display name (e.g. `"Freshness"`).
- `status: CheckStatus` — serialized as lowercase string: `"passed"`, `"warning"`, `"failed"`, `"error"`.
- `message: str` — human-readable explanation.
- `actual_value: object` — the observed number/value.
- `threshold: object` — the limit that was checked.
- `details: dict | None` — free-form extra context.

## Console reporter specifics

- Uses Rich for colored output.
- Degrades gracefully when `stdout` is not a TTY (piped to a file, CI log).
- Shows the banner + trust-score summary + per-check details.
- `report_verbose()` vs `report_summary()` — verbose when single metric or `-v` flag; summary when running a whole directory.

## Adding a new reporter

Owned by the **litmus-advocate** agent:

1. Create `reporters/<format>.py` exporting `generate_<format>_report(results) -> str`.
2. Add the format choice in `cli.py::check` and `cli.py::report` (`click.Choice(["console", "json", "html", "markdown", "<new>"])`).
3. Add an import + dispatch branch in the CLI body.
4. Add a test under `tests/test_reporters/`.

## Design rules

- One input shape, one output type. Don't branch on warehouse or connector — that info is already baked into `CheckResult`.
- Every reporter must handle `CheckStatus.ERROR` distinctly from `CheckStatus.FAILED`. Users need to see connector errors clearly.
- Prefer stable field names over pretty ones; prettiness is a template concern.
- Console reporter should be the clearest. HTML/Markdown/JSON follow its field set.
