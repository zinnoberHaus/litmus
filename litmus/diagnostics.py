"""``litmus doctor`` — verify the setup is complete and working."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def _check(name: str, ok: bool, hint: str = "") -> bool:
    mark = "✓" if ok else "✗"
    line = f"  {mark} {name}"
    if not ok and hint:
        line += f"\n      → {hint}"
    print(line)
    return ok


def run_doctor() -> bool:
    print("Litmus doctor:")
    print()

    results = []

    # Python version
    results.append(_check(
        f"Python {sys.version_info.major}.{sys.version_info.minor}",
        sys.version_info >= (3, 10),
        "Need Python 3.10 or newer.",
    ))

    # Litmus installed
    try:
        import litmus  # noqa: F401
        results.append(_check("litmus package importable", True))
    except ImportError:
        results.append(_check(
            "litmus package importable", False,
            "Run: pip install -e '.[dev]'",
        ))

    # DuckDB installed
    try:
        import duckdb  # noqa: F401
        results.append(_check("duckdb available", True))
    except ImportError:
        results.append(_check("duckdb available", False, "Run: pip install duckdb"))

    # .env exists (warn, don't fail)
    env_exists = Path(".env").exists()
    _check(".env file present", env_exists, "Run: cp .env.example .env")

    # MCP servers reachable (best-effort)
    npx = shutil.which("npx")
    results.append(_check("npx available (for MCP servers)", npx is not None,
                          "Install Node.js to enable Notion/Linear MCP servers."))

    # Optional integrations
    print()
    print("Optional integrations:")
    _check("NOTION_API_KEY set", bool(os.environ.get("NOTION_API_KEY")),
           "Get a key at notion.so/profile/integrations, set in .env")
    _check("LINEAR_API_KEY set", bool(os.environ.get("LINEAR_API_KEY")),
           "Get a key at linear.app/settings/api, set in .env")
    _check(
        "ANTHROPIC_API_KEY set",
        bool(os.environ.get("LITMUS_ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")),
        "Get a key at console.anthropic.com/settings/keys, set in .env",
    )

    print()
    if all(results):
        print("Litmus ready. Try: litmus demo")
        return True
    print("Setup incomplete — fix the items marked ✗ above.")
    return False
