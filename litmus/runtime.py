"""Resolve how to talk to the agent team, based on the model picked in `init`.

The interactive chat and the `ask` / `agent` commands all run through the Claude
Code CLI today (Python — no TypeScript needed). The model the user chose in the
wizard is recorded in ``.litmus/state.json``:

- Claude models → passed through to `claude --print --model <id>`.
- Other providers (GPT / Gemini / local) → a native ``AgentRuntime`` adapter is
  on the roadmap; until then we route through Claude Code and say so once.

This keeps the model menu honest without splitting the codebase: the runtime is
a thin resolver, not a second agent framework.
"""

from __future__ import annotations

import json
from pathlib import Path

STATE_FILE = Path(".litmus/state.json")


def project_model() -> dict:
    """Return the ``model`` block from .litmus/state.json (or {} if absent)."""
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text())
            return dict(data.get("model") or {})
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def claude_model_args() -> list[str]:
    """``['--model', <id>]`` when the project picked a Claude model, else ``[]``."""
    m = project_model()
    if m.get("provider") == "anthropic" and m.get("name"):
        return ["--model", str(m["name"])]
    return []


def runtime_note() -> str | None:
    """One-line heads-up when the picked provider isn't natively wired yet."""
    m = project_model()
    provider = m.get("provider")
    if provider and provider != "anthropic":
        return (
            f"[litmus] model '{m.get('name')}' ({provider}) routes through Claude "
            "Code for now; a native adapter is on the roadmap."
        )
    return None
