"""Tests for SwarmRunner: retries, deadlines, and result finalization."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestrate"))

from conftest import make_result_text  # noqa: E402
from swarm.config import RoleConfig  # noqa: E402
from swarm.runner import (  # noqa: E402
    CloudRunResult,
    CloudStartupError,
    SwarmRunner,
)


class _Client:
    """Configurable fake: a queue of actions per call (exception or result)."""

    def __init__(self, actions):
        self._actions = list(actions)
        self.run_calls = 0
        self.resume_calls = 0

    def _next(self):
        action = self._actions.pop(0)
        if isinstance(action, Exception):
            raise action
        return action

    def run(self, prompt, model, repo, auto_create_pr, timeout_seconds):
        self.run_calls += 1
        return self._next()

    def resume(self, agent_id, prompt, timeout_seconds):
        self.resume_calls += 1
        return self._next()


def _role(**kw):
    defaults = dict(name="scout", model="m", prompt_file="p.md", max_retries=2, timeout_seconds=100)
    defaults.update(kw)
    return RoleConfig(**defaults)


def _finished(text=None):
    return CloudRunResult(
        agent_id="bc-1",
        run_id="r1",
        status="finished",
        text=text or make_result_text("ok", "done", {"x": 1}),
    )


def _runner(client):
    return SwarmRunner(client, clock=lambda: 0.0, sleep=lambda s: None, base_backoff_seconds=1.0)


def test_finished_with_valid_result_is_ok():
    runner = _runner(_Client([_finished()]))
    outcome = runner.run_role(_role(), "prompt", "o/r")
    assert outcome.ok
    assert outcome.result.verdict == "ok"
    assert outcome.attempts == 1


def test_finished_with_malformed_result_is_error():
    runner = _runner(_Client([_finished(text="no result block")]))
    outcome = runner.run_role(_role(), "prompt", "o/r")
    assert not outcome.ok
    assert outcome.status == "error"
    assert "malformed" in outcome.error


def test_terminal_error_status_is_reported():
    bad = CloudRunResult(agent_id="bc", run_id="r", status="error", text="")
    outcome = _runner(_Client([bad])).run_role(_role(), "p", "o/r")
    assert outcome.status == "error"
    assert "status=" in outcome.error


def test_retryable_startup_error_then_success():
    client = _Client([CloudStartupError("net", is_retryable=True), _finished()])
    outcome = _runner(client).run_role(_role(), "p", "o/r")
    assert outcome.ok
    assert outcome.attempts == 2
    assert client.run_calls == 2


def test_non_retryable_startup_error_stops_immediately():
    client = _Client([CloudStartupError("auth", is_retryable=False), _finished()])
    outcome = _runner(client).run_role(_role(), "p", "o/r")
    assert outcome.status == "error"
    assert outcome.attempts == 1
    assert client.run_calls == 1


def test_retries_exhausted_returns_error():
    actions = [CloudStartupError("net", is_retryable=True)] * 5
    outcome = _runner(_Client(actions)).run_role(_role(max_retries=2), "p", "o/r")
    assert outcome.status == "error"
    assert outcome.attempts == 3  # initial + 2 retries


def test_deadline_reached_before_start_is_cancelled():
    # clock is already past the deadline.
    runner = SwarmRunner(_Client([_finished()]), clock=lambda: 100.0, sleep=lambda s: None)
    outcome = runner.run_role(_role(), "p", "o/r", deadline=50.0)
    assert outcome.status == "cancelled"
    assert "deadline" in outcome.error


def test_resume_uses_resume_path():
    client = _Client([_finished()])
    outcome = _runner(client).run_role(_role(), "p", "o/r", resume_agent_id="bc-42")
    assert outcome.ok
    assert client.resume_calls == 1
    assert client.run_calls == 0
