# ADR 0006: Role-separated agent swarm and automated Friday release

## Status

Accepted (v0.1, orchestration round 2)

## Context

ADR 0005 automated the paper-review-to-PR loop with a single scheduled Cursor
cloud agent. The next step asked for more: a small *swarm* of cloud agents
that runs daily inside a fixed morning window (04:00-09:00 Asia/Kolkata),
does something genuinely useful on the repository each day, and - as its
first concrete responsibility - keeps corticore healthy and cuts a new
release every Friday, with an independent, unbiased check over the weekend.

The risk profile of "several agents making changes every day, and publishing
to a package index automatically" is much higher than one weekly, human-gated
PR. Two failure modes dominate:

1. **Unbounded or duplicated work** - agents looping, re-doing interrupted
   work, spending cost without a stop condition, or making sprawling changes.
2. **A bad automated release** - shipping a broken or regressed artifact to
   PyPI with no human in the loop, or an agent grading its own homework.

The design therefore separates *thinking* from *doing* from *judging*, keeps
every genuinely dangerous decision (what version to ship, whether to publish)
a deterministic function of hard signals rather than a model's opinion, and
keeps the whole thing behind kill switches.

## Decision

Add a swarm orchestration layer under `orchestrate/swarm/` plus the workflows
that schedule it, with these load-bearing choices:

1. **Role separation with a single writer.** Parallel read-only *thinker*
   roles (a maintenance scout, a research scout, and a release-risk critic,
   all on a GPT-class reasoning model) propose bounded work. A read-only
   *judge* picks at most one proposal per cycle. Only one role - the
   *executor* (Composer) - can change code and open a PR, and it opens exactly
   one scoped PR and never pushes to the default branch. Config validation
   (`swarm/config.py`) enforces that thinkers/judge/verifier can never be
   granted write access.

2. **An independent, blind verifier.** A separate weekend workflow re-checks
   the week's merged `main` from a clean clone, given only the commit SHA and
   an acceptance rubric - never the planner's or executor's reasoning. It runs
   the full suite, the eval regression gate, and a clean-room package smoke
   test, and opens a `release-blocker` issue on failure. It cannot edit code
   or approve its own candidate. This is the unbiased check the release
   cadence requires.

3. **Fail-closed model selection.** Configured model ids are validated against
   `Cursor.models.list()` before any agent launches; a missing id aborts the
   run rather than silently falling back to a different model
   (`swarm/models.py`).

4. **A hard operating window and cost caps.** `swarm/window.py` computes when
   the swarm may start work and a per-cycle deadline; `run_swarm.py` refuses
   to start new work outside the window. `swarm.yml`'s `budget` caps parallel
   thinkers, code-changing tasks per cycle (default 1), and total runs.

5. **A durable, resumable ledger.** Every step is appended to a ledger
   (`swarm/ledger.py`; GitHub-issue-backed in production). Interrupted
   executor work is found by its in-progress ledger entry and *resumed* via
   the recorded agent id, so long-running or cross-day work is continued, not
   duplicated.

6. **Deterministic, fail-closed release.** The Friday release is fully
   automatic but never model-decided. `orchestrate/prepare_release.py`
   computes the semantic bump from merged change labels
   (`breaking`->major, `feature`->minor, `fix`->patch; none -> no release),
   rolls the CHANGELOG, and opens an auto-merge release PR. Publishing
   (`release.yml`) happens only when every gate in `swarm/gates.py`
   /`evaluate_release_gate` clears: kill switch on, CI green, verifier green,
   CHANGELOG entry present, clean history, no open `release-blocker` issues,
   no existing tag, and PyPI Trusted Publishing configured. Re-runs are
   idempotent.

7. **Kill switches.** `SWARM_ENABLED` (repo variable) gates all code-writing;
   `RELEASE_ENABLED` gates publishing. Either set to anything but `true`
   reduces the system to a safe no-op.

The scheduler remains GitHub Actions (as in ADR 0005) driving the Cursor SDK,
for the same reason: it is zero-additional-infrastructure, versioned in-repo,
and reviewable. Cursor Automations remain a noted alternative not adopted here.

## Consequences

- The single-writer + human/verifier gate preserves ADR 0005's core stance:
  automation is fine, silent unreviewed or unverified changes are not. Nothing
  the swarm does merges or publishes without passing deterministic gates.
- The package version now has a single source of truth in `pyproject.toml`;
  `corticore.__version__` derives from package metadata (with a source
  fallback), removing the previous two-place duplication. A consistency test
  pins this.
- Activation requires one-time external setup that cannot be done from a code
  session (documented in `README.md`): enabling Cursor long-running agents,
  a least-privilege Cursor service-account key, GitHub branch protection +
  auto-merge, repository variables/secrets, and registering the release
  workflow as a PyPI Trusted Publisher. There is currently no `corticore`
  project on PyPI, so trusted-publisher registration must precede the first
  unattended publish.
- All decision logic (config, models, prompts, results, planning, gates,
  window) is pure and unit-tested; the SDK and GitHub are behind injectable
  seams, so the base test suite needs neither a network nor an API key. This
  matches the testing discipline established for the paper loop.
- The swarm deliberately does at most one code-changing task per day and can
  legitimately choose to do nothing. A quiet day is a successful day; this is
  a feature, not a gap, and keeps the blast radius small while the system
  earns trust.
- The FrontisAI Awesome-Self-Improving-Agents list is treated strictly as a
  research input to the scouts, never as code to copy or an authority that can
  override an ADR or the evaluation gate.
