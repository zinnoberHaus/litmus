"""Install the Litmus agent team into a project directory.

The agent team — five subagents, the workflow skills, the Notion + Linear MCP
wiring, and the ``AGENTS.md`` guide — ships inside the wheel under
``litmus/templates`` so a ``pipx install litmus-data`` user gets the whole team
without cloning this repo. Both ``litmus init`` (cli.py) and the bare-``litmus``
TUI call :func:`install_agent_team`, so the two entry points lay down an
identical scaffold — there is one "create a Litmus team here" code path, not two.

Idempotent: existing files are left untouched unless ``force=True``.
"""

from __future__ import annotations

import shutil
from pathlib import Path

TEMPLATES_ROOT = Path(__file__).parent / "templates"

# Top-level docs copied verbatim into the target repo (the team's front door).
_DOCS = ("AGENTS.md",)


def install_agent_team(target: Path, *, force: bool = False) -> dict:
    """Copy the agent-team scaffold from the bundled templates into ``target``.

    Lays down ``.claude/agents/*.md``, ``.claude/skills/<name>/``, ``.mcp.json``,
    and the top-level docs. Returns a summary so callers can report what landed::

        {"agents": int, "skills": int, "mcp": bool, "docs": int}

    Existing files are skipped unless ``force=True``.
    """
    target = Path(target)
    summary = {"agents": 0, "skills": 0, "mcp": False, "docs": 0}

    # 1. Subagent definitions → .claude/agents/*.md
    agent_src = TEMPLATES_ROOT / "claude" / "agents"
    agent_dst = target / ".claude" / "agents"
    if agent_src.exists():
        agent_dst.mkdir(parents=True, exist_ok=True)
        for src in sorted(agent_src.glob("*.md")):
            dst = agent_dst / src.name
            if force or not dst.exists():
                shutil.copy(src, dst)
                # README.md is the team's index, not a subagent — don't count it.
                if src.name.lower() != "readme.md":
                    summary["agents"] += 1

    # 2. Workflow skills → .claude/skills/<name>/
    skill_src = TEMPLATES_ROOT / "claude" / "skills"
    skill_dst = target / ".claude" / "skills"
    if skill_src.exists():
        skill_dst.mkdir(parents=True, exist_ok=True)
        for src_dir in sorted(skill_src.iterdir()):
            if not src_dir.is_dir():
                continue
            dst_dir = skill_dst / src_dir.name
            if dst_dir.exists():
                if not force:
                    continue
                shutil.rmtree(dst_dir)
            shutil.copytree(src_dir, dst_dir)
            summary["skills"] += 1

    # 3. Notion + Linear MCP wiring → .mcp.json
    mcp_src = TEMPLATES_ROOT / "mcp.json"
    mcp_dst = target / ".mcp.json"
    if mcp_src.exists() and (force or not mcp_dst.exists()):
        shutil.copy(mcp_src, mcp_dst)
        summary["mcp"] = True

    # 4. Front-door docs → AGENTS.md
    for doc in _DOCS:
        doc_src = TEMPLATES_ROOT / doc
        doc_dst = target / doc
        if doc_src.exists() and (force or not doc_dst.exists()):
            shutil.copy(doc_src, doc_dst)
            summary["docs"] += 1

    return summary
