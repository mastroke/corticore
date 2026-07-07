"""Tests for orchestrate/run_cloud_agent.py.

`build_prompt` is pure and always tested. The SDK-calling path in `main()`
is only exercised if `cursor_sdk` is installed (`pip install
corticore[orchestrate]`) - otherwise it's skipped, mirroring the pattern
used for the optional embedder/store extras in
tests/test_embedders.py / tests/test_postgres_store.py.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestrate"))

from run_cloud_agent import build_prompt, main  # noqa: E402

_INSTRUCTIONS_PATH = REPO_ROOT / "orchestrate" / "prompts" / "paper_loop_instructions.md"

_SAMPLE_PAPERS = [
    {
        "id": "2602.99999",
        "title": "A Brand New Paper",
        "date": "2026-02",
        "url": "https://arxiv.org/abs/2602.99999",
    }
]


def test_build_prompt_includes_instructions_and_papers():
    prompt = build_prompt(_SAMPLE_PAPERS, _INSTRUCTIONS_PATH)

    assert "corticore paper-loop instructions" in prompt
    assert "2602.99999" in prompt
    assert "A Brand New Paper" in prompt
    # The papers must be valid, re-parseable JSON embedded in the prompt.
    json_start = prompt.index("```json\n") + len("```json\n")
    json_end = prompt.index("\n```", json_start)
    embedded = json.loads(prompt[json_start:json_end])
    assert embedded == _SAMPLE_PAPERS


def test_build_prompt_with_no_new_papers_still_produces_valid_json():
    prompt = build_prompt([], _INSTRUCTIONS_PATH)

    json_start = prompt.index("```json\n") + len("```json\n")
    json_end = prompt.index("\n```", json_start)
    assert json.loads(prompt[json_start:json_end]) == []


def test_main_with_no_new_papers_exits_zero_without_touching_the_sdk(tmp_path, capsys):
    empty_papers_file = tmp_path / "empty.json"
    empty_papers_file.write_text("[]")

    exit_code = main(["--papers-file", str(empty_papers_file)])

    assert exit_code == 0
    assert "nothing to do" in capsys.readouterr().out.lower()


def test_main_dry_run_prints_prompt_without_calling_the_sdk(tmp_path, capsys):
    papers_file = tmp_path / "new_papers.json"
    papers_file.write_text(json.dumps(_SAMPLE_PAPERS))

    exit_code = main(["--papers-file", str(papers_file), "--dry-run"])
    out = capsys.readouterr().out

    assert exit_code == 0
    assert "2602.99999" in out
    assert "dry-run" in out


def test_main_missing_api_key_fails_fast_without_dry_run(tmp_path, monkeypatch, capsys):
    pytest.importorskip("cursor_sdk")
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    papers_file = tmp_path / "new_papers.json"
    papers_file.write_text(json.dumps(_SAMPLE_PAPERS))

    exit_code = main(["--papers-file", str(papers_file)])

    assert exit_code == 1
    assert "CURSOR_API_KEY" in capsys.readouterr().err


def test_main_calls_sdk_and_reports_finished_status(tmp_path, monkeypatch):
    pytest.importorskip("cursor_sdk")
    import cursor_sdk

    class _FakeResult:
        id = "bc-fake123"
        status = "finished"

    calls = {}

    def _fake_prompt(prompt, options):
        calls["prompt"] = prompt
        calls["options"] = options
        return _FakeResult()

    # run_cloud_agent.main() does `from cursor_sdk import Agent` internally on
    # each call, so patching the cursor_sdk module's own attribute is enough.
    monkeypatch.setattr(cursor_sdk.Agent, "prompt", staticmethod(_fake_prompt))
    monkeypatch.setenv("CURSOR_API_KEY", "test-key")

    papers_file = tmp_path / "new_papers.json"
    papers_file.write_text(json.dumps(_SAMPLE_PAPERS))

    exit_code = main(["--papers-file", str(papers_file), "--repo", "mastroke/corticore"])

    assert exit_code == 0
    assert calls["options"].cloud.repos == ["mastroke/corticore"]
