"""Tests for the run_swarm CLI wiring (dry-run, kill switch, guards)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestrate"))

import run_swarm  # noqa: E402


def test_kill_switch_enabled_variants():
    assert run_swarm.kill_switch_enabled({"SWARM_ENABLED": "true"}) is True
    assert run_swarm.kill_switch_enabled({"SWARM_ENABLED": "TRUE"}) is True
    assert run_swarm.kill_switch_enabled({"SWARM_ENABLED": "false"}) is False
    assert run_swarm.kill_switch_enabled({}) is False


def test_dry_run_prints_prompts_without_api_key():
    pytest.importorskip("yaml")
    exit_code = run_swarm.main(["--dry-run", "--task", "corticore-maintenance"], env={})
    assert exit_code == 0


def test_dry_run_captures_all_roles(capsys):
    pytest.importorskip("yaml")
    run_swarm.main(["--dry-run"], env={})
    out = capsys.readouterr().out
    assert "ROLE: maintenance_scout" in out
    assert "ROLE: executor" in out
    assert "no agents launched" in out


def test_live_run_without_api_key_fails_fast():
    pytest.importorskip("yaml")
    exit_code = run_swarm.main([], env={})
    assert exit_code == 1
