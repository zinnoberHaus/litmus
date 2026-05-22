"""Litmus integration adapters.

Thin wrappers over external services:

- ``notion``: push project state to a Notion page (via the Notion MCP server).
- ``linear``: open / update issues (via the Linear MCP server).

The Notion + Linear adapters are deliberately thin — actual writes happen
through the ``ops-pilot`` agent and the MCP servers, not from Python.
These modules define the *payload shape* and helper utilities.
"""

from __future__ import annotations
