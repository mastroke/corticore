"""Tests for the run_swarm CLI wiring (dry-run, kill switch, guards, local loop)."""

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
    assert "MODEL: composer-2.5" in out
    assert "no agents launched" in out


def test_live_run_without_api_key_fails_fast():
    pytest.importorskip("yaml")
    exit_code = run_swarm.main([], env={})
    assert exit_code == 1


def _ist(year, month, day, hour, minute=0):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    return datetime(year, month, day, hour, minute, tzinfo=ZoneInfo("Asia/Kolkata"))


class _ClosedWindow:
    """Stand-in OperatingWindow that is always closed (afternoon IST)."""

    def __init__(self, **_kwargs):
        pass

    def now_local(self, *_a, **_k):
        return _ist(2026, 7, 21, 17, 0)  # Tuesday 17:00 IST — outside 04–09

    def is_open(self, _now):
        return False

    def seconds_until_close(self, _now):
        return 0.0


class _OpenWindow:
    """Stand-in OperatingWindow that is always open with a long deadline."""

    def __init__(self, **_kwargs):
        pass

    def now_local(self, *_a, **_k):
        return _ist(2026, 7, 20, 5, 0)  # Monday morning

    def is_open(self, _now):
        return True

    def seconds_until_close(self, _now):
        return 3600.0


class _FakeReport:
    cycle_id = "cycle-test"
    task = "corticore-maintenance"
    thinker_outcomes = []
    proposals = []
    plan = None
    skipped_reason = None
    pr_url = None
    executor_outcome = None

    def executed(self):
        return False


def _patch_live_deps(monkeypatch, calls, *, window_cls=_ClosedWindow):
    """Stub out every network/side-effecting seam so main() can run offline."""
    monkeypatch.setattr(run_swarm, "list_available_model_ids", lambda _key: [])
    monkeypatch.setattr(run_swarm, "validate_models", lambda _req, _avail: None)
    monkeypatch.setattr(run_swarm, "OperatingWindow", window_cls)
    monkeypatch.setattr(run_swarm, "SwarmRunner", lambda _client: object())
    monkeypatch.setattr(run_swarm, "_build_ledger", lambda _args, _env: object())
    monkeypatch.setattr(run_swarm, "ensure_checkout", lambda path, **_k: Path(path))
    monkeypatch.setattr(run_swarm, "_maybe_cut_release", lambda *_a, **_k: 0)
    monkeypatch.setattr(run_swarm, "mark_ran_today", lambda *_a, **_k: None)
    monkeypatch.setattr(run_swarm, "already_ran_today", lambda *_a, **_k: False)

    import swarm.cursor_client as cc

    monkeypatch.setattr(
        cc, "build_client", lambda runtime, api_key, **kw: type("C", (), {"runtime": runtime})()
    )

    class _FakeOrchestrator:
        def __init__(self, *_a, **_k):
            pass

        def run_cycle(self, task, deadline):
            calls.setdefault("run_cycle_calls", 0)
            calls["run_cycle_calls"] += 1
            calls["run_cycle"] = {"task": task, "deadline": deadline}
            return _FakeReport()

    monkeypatch.setattr(run_swarm, "Orchestrator", _FakeOrchestrator)


def test_closed_window_skips_without_ignore_flag(monkeypatch):
    pytest.importorskip("yaml")
    calls = {}
    _patch_live_deps(monkeypatch, calls)
    exit_code = run_swarm.main([], env={"CURSOR_API_KEY": "k"})
    assert exit_code == 0
    assert "run_cycle" not in calls  # window closed -> no work started


def test_ignore_window_runs_cycle_when_closed(monkeypatch):
    pytest.importorskip("yaml")
    calls = {}
    _patch_live_deps(monkeypatch, calls)
    exit_code = run_swarm.main(
        ["--no-write", "--ignore-window"], env={"CURSOR_API_KEY": "k"}
    )
    assert exit_code == 0
    assert "run_cycle" in calls  # bypassed the closed window and ran


def test_local_loop_stops_at_commit_ceiling(monkeypatch, tmp_path):
    pytest.importorskip("yaml")
    calls = {}
    _patch_live_deps(monkeypatch, calls, window_cls=_OpenWindow)

    # Ceiling already reached -> loop should not start a cycle.
    monkeypatch.setattr(run_swarm, "count_commits_today", lambda *_a, **_k: 40)
    monkeypatch.setattr(
        run_swarm,
        "_run_local_cycle",
        lambda *_a, **_k: calls.setdefault("local_cycles", []).append(1) or 0,
    )

    exit_code = run_swarm.main(
        [
            "--runtime",
            "local",
            "--loop",
            "--checkout",
            str(tmp_path),
            "--stamp-path",
            str(tmp_path / "stamp"),
            "--commit-ceiling",
            "40",
            "--skip-release",
        ],
        env={"CURSOR_API_KEY": "k", "SWARM_ENABLED": "true"},
    )
    assert exit_code == 0
    assert calls.get("local_cycles", []) == []


def test_local_single_cycle_calls_verify_path(monkeypatch, tmp_path):
    pytest.importorskip("yaml")
    calls = {}
    _patch_live_deps(monkeypatch, calls, window_cls=_OpenWindow)

    def _fake_local_cycle(orch, task, deadline, checkout):
        calls["local_cycle"] = {"task": task, "checkout": str(checkout)}
        return 0

    monkeypatch.setattr(run_swarm, "_run_local_cycle", _fake_local_cycle)

    exit_code = run_swarm.main(
        [
            "--runtime",
            "local",
            "--checkout",
            str(tmp_path),
            "--stamp-path",
            str(tmp_path / "stamp"),
            "--skip-release",
            "--no-write",
        ],
        env={"CURSOR_API_KEY": "k"},
    )
    assert exit_code == 0
    assert calls["local_cycle"]["task"] == "corticore-maintenance"


def test_release_day_helper_invoked_for_local(monkeypatch, tmp_path):
    pytest.importorskip("yaml")
    calls = {}
    _patch_live_deps(monkeypatch, calls, window_cls=_ClosedWindow)

    def _fake_release(config, checkout, window):
        calls["release"] = True
        return 0

    monkeypatch.setattr(run_swarm, "_maybe_cut_release", _fake_release)

    # Outside window, local, not skip-release -> still attempts release-day check.
    exit_code = run_swarm.main(
        ["--runtime", "local", "--checkout", str(tmp_path)],
        env={"CURSOR_API_KEY": "k"},
    )
    assert exit_code == 0
    assert calls.get("release") is True


def test_already_ran_today_stamp(tmp_path):
    stamp = tmp_path / "last_run_day"
    assert run_swarm.already_ran_today(stamp, "2026-07-21") is False
    run_swarm.mark_ran_today(stamp, "2026-07-21")
    assert run_swarm.already_ran_today(stamp, "2026-07-21") is True
    assert run_swarm.already_ran_today(stamp, "2026-07-22") is False


def test_catch_up_runs_when_stamp_missing(monkeypatch, tmp_path):
    pytest.importorskip("yaml")
    calls = {}
    _patch_live_deps(monkeypatch, calls, window_cls=_ClosedWindow)
    stamp = tmp_path / "stamp"

    def _real_mark(path, today_iso):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(today_iso + "\n")
        calls["stamped"] = today_iso

    def _real_already(path, today_iso):
        try:
            return path.read_text().strip() == today_iso
        except OSError:
            return False

    monkeypatch.setattr(run_swarm, "mark_ran_today", _real_mark)
    monkeypatch.setattr(run_swarm, "already_ran_today", _real_already)

    def _fake_local_cycle(orch, task, deadline, checkout):
        calls["catch_up_cycle"] = True
        return 0

    monkeypatch.setattr(run_swarm, "_run_local_cycle", _fake_local_cycle)
    monkeypatch.setattr(run_swarm, "count_commits_today", lambda *_a, **_k: 0)

    exit_code = run_swarm.main(
        [
            "--runtime",
            "local",
            "--catch-up",
            "--checkout",
            str(tmp_path / "co"),
            "--stamp-path",
            str(stamp),
            "--skip-release",
        ],
        env={"CURSOR_API_KEY": "k", "SWARM_ENABLED": "true"},
    )
    assert exit_code == 0
    assert calls.get("catch_up_cycle") is True
    assert calls.get("stamped") == "2026-07-21"


def test_catch_up_skips_when_already_stamped(monkeypatch, tmp_path):
    pytest.importorskip("yaml")
    calls = {}
    _patch_live_deps(monkeypatch, calls, window_cls=_ClosedWindow)
    stamp = tmp_path / "stamp"
    monkeypatch.setattr(run_swarm, "already_ran_today", lambda *_a, **_k: True)

    def _fake_local_cycle(*_a, **_k):
        calls["cycle"] = True
        return 0

    monkeypatch.setattr(run_swarm, "_run_local_cycle", _fake_local_cycle)

    exit_code = run_swarm.main(
        [
            "--runtime",
            "local",
            "--catch-up",
            "--checkout",
            str(tmp_path),
            "--stamp-path",
            str(stamp),
            "--skip-release",
        ],
        env={"CURSOR_API_KEY": "k"},
    )
    assert exit_code == 0
    assert "cycle" not in calls


def test_competitors_yml_lists_peers():
    yaml = pytest.importorskip("yaml")
    path = REPO_ROOT / "orchestrate" / "competitors.yml"
    data = yaml.safe_load(path.read_text())
    names = {c["name"] for c in data["competitors"]}
    assert "mem0" in names
    assert "awesome-self-improving-agents" in names


def test_research_scout_prompt_requires_competitor_fallback():
    text = (
        REPO_ROOT / "orchestrate" / "prompts" / "swarm" / "research_scout.md"
    ).read_text()
    assert "competitors.yml" in text
    assert "competitor analysis" in text.lower() or "Competitor analysis" in text
    assert "kind: competitor" in text
