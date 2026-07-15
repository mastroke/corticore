"""Tests for the deterministic release gate and version bump (pure)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestrate"))

from swarm.gates import (  # noqa: E402
    ReleaseGateInput,
    bump_type,
    evaluate_release_gate,
    has_releasable_changes,
    next_version,
)


def test_bump_type_precedence():
    assert bump_type(["fix", "feature", "breaking"]) == "major"
    assert bump_type(["fix", "feature"]) == "minor"
    assert bump_type(["fix"]) == "patch"
    assert bump_type(["docs", "chore"]) is None


def test_has_releasable_changes():
    assert has_releasable_changes(["feature"]) is True
    assert has_releasable_changes(["docs"]) is False


@pytest.mark.parametrize(
    "current,bump,expected",
    [
        ("0.1.0", "patch", "0.1.1"),
        ("0.1.0", "minor", "0.2.0"),
        ("0.1.0", "major", "1.0.0"),
        ("1.4.9", "patch", "1.4.10"),
    ],
)
def test_next_version(current, bump, expected):
    assert next_version(current, bump) == expected


def test_next_version_rejects_bad_input():
    with pytest.raises(ValueError):
        next_version("0.1", "patch")
    with pytest.raises(ValueError):
        next_version("0.1.0", "bogus")


def _all_clear() -> ReleaseGateInput:
    return ReleaseGateInput(
        release_enabled=True,
        ci_passed=True,
        verifier_passed=True,
        changelog_ready=True,
        working_tree_clean=True,
        model_validated=True,
        pypi_trusted_publisher=True,
        has_releasable_changes=True,
        blocking_issues_open=False,
        security_alerts_open=False,
        tag_already_exists=False,
        version_already_on_index=False,
    )


def test_gate_allows_when_all_clear():
    decision = evaluate_release_gate(_all_clear())
    assert decision.allowed is True
    assert decision.reasons == []


def test_gate_defaults_block():
    # Default input is the fully-blocking state.
    decision = evaluate_release_gate(ReleaseGateInput())
    assert decision.allowed is False
    assert len(decision.reasons) >= 5


def test_gate_collects_all_blocking_reasons():
    inp = _all_clear()
    blocked = ReleaseGateInput(
        **{**inp.__dict__, "ci_passed": False, "tag_already_exists": True}
    )
    decision = evaluate_release_gate(blocked)
    assert decision.allowed is False
    joined = " ".join(decision.reasons)
    assert "CI" in joined
    assert "tag" in joined


def test_gate_blocks_on_kill_switch_off():
    inp = _all_clear()
    off = ReleaseGateInput(**{**inp.__dict__, "release_enabled": False})
    assert evaluate_release_gate(off).allowed is False
