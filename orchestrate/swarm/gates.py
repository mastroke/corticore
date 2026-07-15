"""Deterministic release-gate and version-bump logic (pure, fail-closed).

The Friday release is fully automatic, which only stays safe if the decision
to publish is a boring, auditable function of hard signals - never a model's
opinion. Everything here is a pure function over booleans and strings so it
can be exhaustively unit-tested and so the workflow can print exactly why a
release was allowed or blocked.

Guiding principle: fail closed. Any missing, unknown, or negative signal
blocks the release; only an explicit all-clear proceeds.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional

# Labels that drive the semantic bump. Applied to merged PRs during the week.
LABEL_MAJOR = "breaking"
LABEL_MINOR = "feature"
LABEL_PATCH = "fix"

_RELEASE_RELEVANT_LABELS = {LABEL_MAJOR, LABEL_MINOR, LABEL_PATCH}


def bump_type(labels: Iterable[str]) -> Optional[str]:
    """Pick the semantic bump for a set of merged-change labels.

    `breaking` wins over `feature` wins over `fix`. Returns None when no
    release-relevant label is present, which the caller treats as "nothing to
    release this cycle".
    """
    label_set = {str(label).strip().lower() for label in labels}
    if LABEL_MAJOR in label_set:
        return "major"
    if LABEL_MINOR in label_set:
        return "minor"
    if LABEL_PATCH in label_set:
        return "patch"
    return None


def has_releasable_changes(labels: Iterable[str]) -> bool:
    """True if any label maps to a real semver bump."""
    return bump_type(labels) is not None


def next_version(current: str, bump: str) -> str:
    """Compute the next semver string. Rejects non-`X.Y.Z` inputs loudly."""
    parts = current.strip().split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise ValueError(f"version must be MAJOR.MINOR.PATCH, got: {current!r}")
    major, minor, patch = (int(p) for p in parts)
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    if bump == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"unknown bump type: {bump!r}")


@dataclass(frozen=True)
class ReleaseGateInput:
    """Every hard signal the release decision depends on.

    Booleans are phrased so that the *safe* default is the one that blocks:
    anything the workflow can't positively confirm should be passed as the
    blocking value (e.g. `ci_passed=False`, `tag_exists=True`).
    """

    release_enabled: bool = False
    ci_passed: bool = False
    verifier_passed: bool = False
    changelog_ready: bool = False
    working_tree_clean: bool = False
    model_validated: bool = False
    pypi_trusted_publisher: bool = False
    has_releasable_changes: bool = False
    blocking_issues_open: bool = True
    security_alerts_open: bool = True
    tag_already_exists: bool = True
    version_already_on_index: bool = True


@dataclass(frozen=True)
class ReleaseDecision:
    allowed: bool
    reasons: List[str]

    def blocking_reasons(self) -> List[str]:
        return list(self.reasons)


def evaluate_release_gate(inp: ReleaseGateInput) -> ReleaseDecision:
    """Return whether an automated release may proceed, and why not if it can't.

    Collects *all* blocking reasons (not just the first) so a single run
    surfaces everything an operator would need to fix.
    """
    reasons: List[str] = []

    if not inp.release_enabled:
        reasons.append("release kill switch is off (RELEASE_ENABLED != true)")
    if not inp.has_releasable_changes:
        reasons.append("no release-relevant labelled changes this cycle")
    if not inp.ci_passed:
        reasons.append("required CI checks did not pass")
    if not inp.verifier_passed:
        reasons.append("independent blind verifier did not pass")
    if not inp.changelog_ready:
        reasons.append("CHANGELOG entry for the new version is missing")
    if not inp.working_tree_clean:
        reasons.append("git working tree/history is not clean")
    if not inp.model_validated:
        reasons.append("configured model ids were not validated")
    if not inp.pypi_trusted_publisher:
        reasons.append("PyPI Trusted Publishing is not configured")
    if inp.blocking_issues_open:
        reasons.append("one or more blocking issues are open")
    if inp.security_alerts_open:
        reasons.append("open dependency/security alerts")
    if inp.tag_already_exists:
        reasons.append("a git tag for this version already exists")
    if inp.version_already_on_index:
        reasons.append("this version is already published on the index")

    return ReleaseDecision(allowed=not reasons, reasons=reasons)
