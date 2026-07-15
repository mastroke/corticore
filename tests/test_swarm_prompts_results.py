"""Tests for prompt assembly and result-block parsing (pure)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestrate"))

from swarm.prompts import RESULT_BEGIN, RESULT_END, assemble_prompt  # noqa: E402
from swarm.results import (  # noqa: E402
    MalformedResultError,
    parse_agent_result,
    parse_agent_result_lenient,
)


def test_assemble_prompt_includes_context_and_contract():
    prompt = assemble_prompt("PLAYBOOK", {"task": "t1", "role": "scout"})
    assert "PLAYBOOK" in prompt
    assert '"task": "t1"' in prompt
    assert RESULT_BEGIN in prompt
    assert RESULT_END in prompt


def test_parse_valid_result():
    text = (
        f"analysis\n{RESULT_BEGIN}\n```json\n"
        '{"verdict": "execute", "summary": "do it", "data": {"x": 1}}'
        f"\n```\n{RESULT_END}\n"
    )
    result = parse_agent_result(text)
    assert result.verdict == "execute"
    assert result.summary == "do it"
    assert result.data == {"x": 1}


def test_parse_result_without_fence():
    text = (
        f"{RESULT_BEGIN}\n"
        '{"verdict": "pass", "summary": "ok"}'
        f"\n{RESULT_END}"
    )
    result = parse_agent_result(text)
    assert result.verdict == "pass"
    assert result.data == {}


def test_missing_begin_marker_raises():
    with pytest.raises(MalformedResultError, match="missing"):
        parse_agent_result("no markers here")


def test_missing_end_marker_raises():
    with pytest.raises(MalformedResultError, match="closing"):
        parse_agent_result(f"{RESULT_BEGIN}\n{{}}")


def test_invalid_json_raises():
    text = f"{RESULT_BEGIN}\nnot json\n{RESULT_END}"
    with pytest.raises(MalformedResultError, match="not valid JSON"):
        parse_agent_result(text)


def test_missing_verdict_raises():
    text = f'{RESULT_BEGIN}\n{{"summary": "x"}}\n{RESULT_END}'
    with pytest.raises(MalformedResultError, match="verdict"):
        parse_agent_result(text)


def test_non_object_data_raises():
    text = f'{RESULT_BEGIN}\n{{"verdict": "v", "summary": "s", "data": 3}}\n{RESULT_END}'
    with pytest.raises(MalformedResultError, match="'data'"):
        parse_agent_result(text)


def test_lenient_returns_none_on_malformed():
    assert parse_agent_result_lenient("garbage") is None
