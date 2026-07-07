# ADR 0005: Scheduled Cursor cloud agent for the paper-review-to-PR loop

## Status

Accepted (v0.1, orchestration round)

## Context

The founding discussion for corticore asked for the paper -> distill ->
decide -> build -> eval-gate loop (see `research/design/DESIGN.md`) to
eventually run itself, rather than staying a manual process a human repeats
every round. By the end of the depth round, that loop had been run twice by
hand and had a stable, repeatable shape: fetch new papers from
[Agent-Memory-Paper-List](https://github.com/Shichun-Liu/Agent-Memory-Paper-List),
write a distilled note per paper, decide adopt/defer/reject against the same
zero-setup + forgetting-first bar every time, implement anything adopted
with tests and a new ADR, check `eval/harness.py` against a baseline, and
open a PR. A process repeatable enough to describe precisely is repeatable
enough to automate.

Two real mechanisms exist to run an agent unattended: native **Cursor
Automations** (event/schedule-triggered runs configured from the Agents
Window) and the **Cursor SDK** called from a scheduler that already runs
somewhere — in this project's case, GitHub Actions, since the repo lives on
GitHub and Actions' cron is a well-understood, zero-additional-infra
scheduler. Automations require the Agents Window to configure and weren't
reachable from this build session's toolset; the SDK is directly callable
from a script, which is what this session can actually produce and verify
end-to-end (including a real, non-mocked dry run — see Verification below).

## Decision

Add a GitHub Actions workflow (`.github/workflows/paper-loop.yml`) that:

1. Runs on a weekly cron (Mondays 09:00 UTC) and on manual `workflow_dispatch`.
2. Runs `orchestrate/check_new_papers.py` — a network-only, dependency-light
   check (stdlib `urllib.request` + `pyyaml`) that parses the paper list and
   diffs it against `research/papers.yaml`, filtered to the project's fixed
   `2026-01` scope cutoff (see `research/design/DESIGN.md`; this is a
   deliberate project-scope decision, not a value to derive or tune).
3. **Only if new papers were found**, runs `orchestrate/run_cloud_agent.py`,
   which calls the Python Cursor SDK's one-shot `Agent.prompt(...)` with
   `cloud=CloudAgentOptions(repos=["mastroke/corticore"], auto_create_pr=True)`.
   This runs on a Cursor-hosted VM against a fresh clone — not this
   workflow's own runner — and, on success, opens a PR. It never pushes to
   `main` directly, matching every other autonomy boundary in this project
   (ADR 0002's forgetting-is-not-silent-deletion stance applies the same
   principle: automation is fine, silent unreviewed changes are not).
4. The cloud agent's instructions live in a versioned prompt file,
   `orchestrate/prompts/paper_loop_instructions.md`, rather than being
   inlined in the workflow or the launcher script — so the playbook itself
   is reviewable, diffable, and can improve over time exactly like the code
   it produces.
5. `eval/BASELINE.md` is introduced as the single source of truth for "is
   this run a regression?" — the prompt instructs the cloud agent to compare
   its `eval/harness.py` run against it and update it (or justify a
   regression) before opening the PR, rather than opening PRs with no eval
   signal attached.

Gating on "any new papers?" before spending a cloud-agent run (rather than
launching one every week regardless) keeps the loop cheap to leave running
indefinitely — the check step costs one HTTP request and no LLM calls.

## Consequences

- Activation requires three manual, one-time steps outside this repo's code
  (documented in the plan and `README.md`): push the repo to GitHub, add a
  `CURSOR_API_KEY` repository secret, and grant Cursor's GitHub integration
  access to the repo. None of this is buildable from a local session without
  a live repo and a real key, so it's explicitly out of scope for this ADR's
  verification.
- `orchestrate/check_new_papers.py`'s parser only recognizes papers whose
  entry links to an `arxiv.org/abs/<id>` URL, since that's the id scheme
  `research/papers.yaml` already uses. Entries linking elsewhere (OpenReview,
  ACL Anthology, publisher DOIs) are silently skipped rather than assigned an
  invented id — a known, accepted gap; a future ADR can extend the id scheme
  if this starts missing real papers.
- The `orchestrate` extra (`cursor-sdk`, `pyyaml`) is additive and optional —
  installing the base package or any other extra is unaffected, preserving
  ADR 0001's zero-setup guarantee for `pip install corticore`.
- Every cloud-agent run's output is still a PR, not a merge: the human
  review gate that's applied to every hand-run round so far is preserved
  exactly, not relaxed, by automating everything upstream of it.
- If the paper list's markdown structure changes, `parse_papers()` will
  silently return fewer (or zero) papers rather than erroring loudly — this
  is a known trade-off of regex-based parsing over a fixed source with no
  API; `tests/test_check_new_papers.py` pins the current format so a future
  format change surfaces as a test failure during development rather than a
  silent gap in production.
