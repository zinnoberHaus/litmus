"""AI-powered helpers for the Litmus server.

Currently houses the run-explanation worker (:mod:`litmus_api.ai.explain`).
Kept under a dedicated subpackage so the Anthropic SDK import is localized —
operators who don't install the ``[ai]`` extra can still boot the server.
"""

from __future__ import annotations

from litmus_api.ai.explain import (
    DEFAULT_MODEL_ID,
    ExplanationPayload,
    explain_run,
)

__all__ = ["DEFAULT_MODEL_ID", "ExplanationPayload", "explain_run"]
