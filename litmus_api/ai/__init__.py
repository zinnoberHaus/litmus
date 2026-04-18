"""AI-powered helpers for the Litmus server.

Two engines live here:

* :mod:`litmus_api.ai.explain` — hypothesis + suggested action for a failed run
  (opt-in per install, mirrors the ``POST /runs/{id}/explain`` route).
* :mod:`litmus_api.ai.ask` — natural-language Q&A over the metric catalog
  (powers ``POST /api/v1/ask`` and the Slack ``app_mention`` handler).

Both gate on ``[ai]`` extras + ``LITMUS_ANTHROPIC_API_KEY``. Kept under a
dedicated subpackage so the Anthropic SDK import is localized — operators
who don't install the extra can still boot the server.
"""

from __future__ import annotations

from litmus_api.ai.ask import (
    AskAnswer,
    AskError,
    answer_question,
)
from litmus_api.ai.explain import (
    DEFAULT_MODEL_ID,
    ExplanationPayload,
    explain_run,
)

__all__ = [
    "DEFAULT_MODEL_ID",
    "ExplanationPayload",
    "explain_run",
    "AskAnswer",
    "AskError",
    "answer_question",
]
