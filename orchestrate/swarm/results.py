"""Parsing the machine-readable result block agents are required to emit.

Agents end their reply with a `<<<SWARM_RESULT>>> ...json... <<<END_SWARM_RESULT>>>`
block (see `prompts._result_contract`). This module extracts and validates
it. A missing or malformed block is a hard error, not a shrug: the
orchestrator treats an unparseable result the same as a failed run, so a
confused agent can never be mistaken for a passing one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from .prompts import RESULT_BEGIN, RESULT_END


class MalformedResultError(ValueError):
    """Raised when an agent reply lacks a valid, parseable result block."""


@dataclass(frozen=True)
class AgentResult:
    """A parsed, validated agent result block."""

    verdict: str
    summary: str
    data: Dict[str, Any] = field(default_factory=dict)
    raw: str = ""


def _extract_json_block(text: str) -> str:
    begin = text.find(RESULT_BEGIN)
    if begin == -1:
        raise MalformedResultError(
            f"agent reply is missing the {RESULT_BEGIN} result marker"
        )
    end = text.find(RESULT_END, begin)
    if end == -1:
        raise MalformedResultError(
            f"agent reply has {RESULT_BEGIN} but no closing {RESULT_END} marker"
        )
    inner = text[begin + len(RESULT_BEGIN) : end]

    # Tolerate an optional ```json fence inside the sentinels.
    fence = "```"
    if fence in inner:
        start_fence = inner.find(fence)
        after = inner.find("\n", start_fence)
        close_fence = inner.rfind(fence)
        if after != -1 and close_fence > after:
            inner = inner[after + 1 : close_fence]
    return inner.strip()


def parse_agent_result(text: str) -> AgentResult:
    """Extract and validate the result block from an agent's final reply."""
    payload = _extract_json_block(text)
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise MalformedResultError(
            f"result block is not valid JSON: {exc}"
        ) from exc

    if not isinstance(parsed, dict):
        raise MalformedResultError("result block must be a JSON object")

    verdict = parsed.get("verdict")
    summary = parsed.get("summary")
    if not isinstance(verdict, str) or not verdict.strip():
        raise MalformedResultError("result block missing non-empty 'verdict'")
    if not isinstance(summary, str) or not summary.strip():
        raise MalformedResultError("result block missing non-empty 'summary'")

    data = parsed.get("data", {})
    if not isinstance(data, dict):
        raise MalformedResultError("'data' must be a JSON object when present")

    return AgentResult(verdict=verdict.strip(), summary=summary.strip(), data=data, raw=text)


def parse_agent_result_lenient(text: str) -> Optional[AgentResult]:
    """Like `parse_agent_result` but returns None instead of raising.

    Useful where a caller wants to distinguish "no result" from a failure
    without a try/except at the call site.
    """
    try:
        return parse_agent_result(text)
    except MalformedResultError:
        return None
