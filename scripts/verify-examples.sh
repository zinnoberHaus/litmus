#!/usr/bin/env bash
# Reproduce the Examples smoke test (.github/workflows/examples.yml) locally.
#
# Runs every example end-to-end:
#   - warehouse/{csv,duckdb,sqlite,excel}: seed → litmus check (expect exit 0)
#   - alignment: seed → litmus check (expect intentional failure on amount nulls)
#
# Exits non-zero if any example doesn't behave as expected, so this can
# gate commits before pushing.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# Collect failures so we see all broken examples in one pass, not just the first.
failures=()

color_red="$(printf '\033[31m')"
color_green="$(printf '\033[32m')"
color_yellow="$(printf '\033[33m')"
color_reset="$(printf '\033[0m')"

_log()  { printf '%s[verify]%s %s\n' "$color_yellow" "$color_reset" "$*"; }
_pass() { printf '%s✓%s %s\n' "$color_green" "$color_reset" "$*"; }
_fail() { printf '%s✗%s %s\n' "$color_red" "$color_reset" "$*"; failures+=("$1"); }

# ---------------------------------------------------------------------------
# Warehouse matrix: each example should exit 0 (healthy or warnings only).
# ---------------------------------------------------------------------------

for example in csv duckdb sqlite excel; do
    dir="examples/warehouses/$example"
    _log "warehouse: $example"

    if ! (cd "$dir" && ./setup.sh >/tmp/litmus-verify-seed.log 2>&1); then
        _fail "$example (seed failed — see /tmp/litmus-verify-seed.log)"
        continue
    fi

    metric=$(ls "$dir"/*.metric | head -1)
    if ! (cd "$dir" && litmus check "$(basename "$metric")" \
            --format json --output /tmp/litmus-verify-report.json \
            >/tmp/litmus-verify-check.log 2>&1); then
        _fail "$example (check exited non-zero — see /tmp/litmus-verify-check.log)"
        continue
    fi

    _pass "$example"
done

# ---------------------------------------------------------------------------
# Alignment demo: intentional red. We expect a null-rate failure on `amount`.
# ---------------------------------------------------------------------------

_log "alignment demo (expects intentional failure)"

(
    cd examples/alignment
    rm -f alignment_demo.duckdb
    python - <<'PY' >/tmp/litmus-verify-seed.log 2>&1
import duckdb
sql = open("seed.sql").read()
duckdb.connect("alignment_demo.duckdb").execute(sql)
PY
) || {
    _fail "alignment (seed failed — see /tmp/litmus-verify-seed.log)"
}

# `litmus check` returns exit 1 when a rule fails — that's the expected path
# here. We care that the specific `amount` null-rate rule is the failing one.
(cd examples/alignment \
    && litmus check metrics/monthly_revenue.metric \
        --format json --output /tmp/litmus-verify-report.json \
        >/tmp/litmus-verify-check.log 2>&1 || true)

python - <<'PY'
import json, sys
try:
    data = json.load(open("/tmp/litmus-verify-report.json"))
except Exception as exc:
    print(f"report missing or invalid: {exc}")
    sys.exit(1)
fails = [c["name"] for m in data["metrics"] for c in m["checks"] if c["status"] == "failed"]
if not any("amount" in n for n in fails):
    print(f"alignment demo didn't fail as expected (got: {fails})")
    sys.exit(1)
PY

if [[ $? -ne 0 ]]; then
    _fail "alignment (intentional red rule didn't fire)"
else
    _pass "alignment (amount null-rate failure confirmed)"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

echo
if [[ ${#failures[@]} -eq 0 ]]; then
    printf '%sAll examples verified.%s\n' "$color_green" "$color_reset"
    exit 0
fi

printf '%s%d example(s) failed:%s\n' "$color_red" "${#failures[@]}" "$color_reset"
for f in "${failures[@]}"; do
    printf '  - %s\n' "$f"
done
exit 1
