"""Litmus integration adapters.

Thin wrappers over external services:

- ``trust``: run trust checks against tables the pipelines produce
  (wraps the core ``litmus.checks`` runner with mart-table conventions).
- ``notion``: push project state to a Notion page (via the Notion MCP server).
- ``linear``: open / update issues (via the Linear MCP server).

The Notion + Linear adapters are deliberately thin — actual writes happen
through the ``ops-pilot`` agent and the MCP servers, not from Python.
These modules define the *payload shape* and helper utilities.
"""

from __future__ import annotations
