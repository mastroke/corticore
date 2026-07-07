---
name: corticore-feature-builder
description: Research, evaluate, and implement corticore features from feature-list.csv. Use when selecting backlog features, comparing competitor implementations (Mem0, Zep/Graphiti, Letta, LangGraph Stores), deciding vision fit, implementing accepted features, or preparing production-grade PRs for corticore.
---

# Corticore Feature Builder

## Purpose

Build corticore from a tracked feature backlog, not from ad-hoc ideas. Every
implementation starts from [`feature-list.csv`](../../../feature-list.csv),
compares competitor behavior, verifies alignment with corticore's vision, and
produces production-grade code with tests and documentation.

## Corticore Vision

Corticore is a local-first, inspectable memory layer for AI agents. Preserve
these principles in every feature:

- SQLite works by default; no required server, vector database, or graph database.
- Forgetting is intentional (`dynamics/decay.py`, `dynamics/consolidate.py`), not an afterthought.
- Memory behavior is explainable through `why()` traces.
- Optional extras (`st`, `openai`, `postgres`) stay opt-in and swap in behind existing interfaces (`stores/base.py::MemoryStore`, `embeddings/base.py::Embedder`).
- Features should improve agent memory without turning corticore into a heavy agent runtime (that is Letta's job) or a hosted platform (that is Mem0/Zep's job).

## Workflow

1. Open `feature-list.csv`.
2. Select one row with `status` in `idea`, `researching`, or `accepted`. Prefer higher `priority` and satisfied `dependencies`.
3. Read `source_repo`, `source_url`, and `competitor_behavior` for that row.
4. Research how the competitor actually implements the behavior (read their docs/README, or source if cloned locally).
5. Re-check `vision_fit` against the Corticore Vision section above. If a feature no longer fits, set `status` to `rejected` and write the reason in `review_notes`; stop there.
6. If it fits, design the smallest production-grade version consistent with corticore's existing architecture (thin `Memory` facade, logic in `dynamics/`/`trace/`/`stores/`/`embeddings/`).
7. Implement behind existing abstractions. Do not break the zero-dependency default path (`Memory("agent.db")` with no args).
8. Add focused tests in `tests/` matching the feature's `acceptance_criteria` and `test_plan` columns.
9. Run the validation commands below.
10. Update docs (`README.md`, `eval/BASELINE.md`) if the public API or benchmark results changed.
11. Update the CSV row: `status=implementing` while in progress, `status=done` when merged; fill in `branch_name`, `pr_url`, `updated_at`.
12. Prepare a PR using the PR Output template below.

## Acceptance Rules

Never implement a feature only because a competitor has it. Accept a feature
only if it improves at least one of:

- recall quality
- memory lifecycle management (decay, consolidation, expiry)
- explainability (`why()` / trace events)
- local-first usability (zero-setup default path)
- production reliability (migrations, error handling, observability)
- evaluation coverage (`eval/harness.py`, `eval/BASELINE.md`)
- backend or embedder extensibility

Reject anything that requires a required server/database by default, or that
turns corticore into a full agent runtime rather than a memory layer other
frameworks depend on.

## Validation Commands

Run from the repo root before committing:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m pytest
PYTHONPATH=src .venv/bin/python eval/harness.py
```

Compare the eval output against the last row in `eval/BASELINE.md`. Same or
better: update `BASELINE.md` with the new score, date, and a one-line note.
Worse: fix the regression, or explicitly document the accepted tradeoff in
both `BASELINE.md` and the PR description. Never let a regression pass silently.

## Production Checklist

Before finishing:

- [ ] New tests cover normal behavior and edge cases.
- [ ] Existing tests pass (`pytest`).
- [ ] `eval/harness.py` does not regress unless explicitly justified.
- [ ] SQLite remains the dependency-free default backend.
- [ ] Optional integrations (`st`, `openai`, `postgres`) stay optional.
- [ ] Trace events (`TraceEvent`) explain any new lifecycle behavior.
- [ ] No secrets or credentials are committed (env vars only, see `.env.example` pattern).
- [ ] `feature-list.csv` row updated with final status and links.

## PR Output

```markdown
## Summary
- What changed
- Why it belongs in corticore (cite the feature-list.csv row)

## Competitor Reference
- Source repo:
- Relevant behavior:

## Test Plan
- Commands run
- Eval result (before/after)

## Risk
- Compatibility risk
- Follow-up work
```
