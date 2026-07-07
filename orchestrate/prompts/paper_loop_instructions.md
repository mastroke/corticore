# corticore paper-loop instructions

You are running as a scheduled, autonomous contributor to the `corticore`
repository - a zero-setup, forgetting-first, fully-inspectable memory layer
for AI agents. This is not a fresh design exercise: it is the automation of
a process a human has already run twice by hand (see the git history and
`research/notes/`). Follow it faithfully rather than reinventing it.

## Context to read first

- `research/design/DESIGN.md` - positioning, architecture, and what's explicitly deferred.
- Every file in `research/design/adr/` - the project's accepted decisions. Treat these as binding constraints, not suggestions. In particular:
  - ADR 0001: the default `Memory()` path must stay zero-setup (no required external services, no required third-party dependency).
  - ADR 0002: forgetting is a first-class, always-on mechanism - don't add features that make memory only ever accumulate.
  - ADR 0003, 0004: examples of the adopt/defer pattern this loop should keep following.
- `research/papers.yaml` and `research/notes/TEMPLATE.md` - the tracking format and note format to reuse exactly.

## New papers for this run

The papers to review this run are provided separately (injected by
`orchestrate/run_cloud_agent.py` as a JSON list of `{id, title, date, url}`
immediately following this document). If that list is empty, stop - there
is nothing to do this run.

## What to do, per paper

1. Fetch the paper's abstract (its arXiv abstract page, `https://arxiv.org/abs/<id>`).
2. Write a distilled note at `research/notes/<id>-<short-slug>.md`, following the structure in `research/notes/TEMPLATE.md` exactly (Problem / Mechanism / What's reusable for corticore / Setup cost / Decision).
3. Decide **adopt**, **defer**, or **reject**, using the same bar applied in every existing note:
   - **Adopt** only if the idea is compatible with the zero-setup default (no new required infrastructure or dependency on the default path) and is genuinely new relative to what corticore already does - not just a restatement of something already implemented.
   - **Defer** if the idea is real but requires infrastructure incompatible with this round's scope (e.g. a graph database, RL training, a learned policy) - say so explicitly and name what a cheaper first step might look like, the way `research/notes/2601.04726-compassmem.md` and `research/notes/2601.03192-memrl.md` do.
   - **Reject** only if the idea doesn't fit corticore's scope at all.
4. Update `research/papers.yaml`: move the paper's `status` to `noted` (defer/reject) or `adopted`, and fill in its `note` (and `adr`, if adopted) fields.

## If you adopt anything

1. Implement the smallest reasonable change that captures the idea - prefer one clean, additive feature per adopted paper over a broad rewrite.
2. Add or extend tests covering the new behavior. Every new optional dependency (a new backend, a new embedder) must be lazy-imported with a clear install-hint `ImportError`, and its tests must use `pytest.importorskip(...)` so the base test suite never fails when the extra isn't installed.
3. Write a new ADR at `research/design/adr/NNNN-<slug>.md`, where `NNNN` is one more than the highest number currently in that directory. Follow the existing ADRs' structure (Status / Context / Decision / Consequences) and cite the paper by arXiv id.
4. **Never edit the body of an existing ADR.** ADRs are an append-only decision log; if a past decision needs revisiting, write a new ADR that supersedes it and say so explicitly, rather than rewriting history.
5. Update `README.md` and/or `research/design/DESIGN.md` only if the change is user-facing enough to belong there (new extras, new public API surface) - don't pad the diff with unrelated doc churn.

## Before opening a PR (required, every run)

1. `pip install -e ".[dev]"` and run `pytest` - the full suite (including everything that already existed) must pass. If you added an optional dependency, also install its extra and confirm its tests run (not just skip) at least once locally in this run.
2. Run `python eval/harness.py` and compare its `recall@k` score against the value recorded in `eval/BASELINE.md`.
   - If the score is the same or better: update `eval/BASELINE.md` with the new score, date, and a one-line note of what changed (or "no change" if nothing affected retrieval).
   - If the score is worse: either fix the regression before opening the PR, or - only if the regression is an intentional, understood tradeoff - state exactly why in both `eval/BASELINE.md` and the PR description. Never let a regression pass silently.
3. Keep the diff scoped to what's justified by the papers reviewed this run. No unrelated refactors, no dependency bumps, no reformatting of untouched files.

## Opening the PR

Open exactly one PR for this run (not one per paper) titled something like
`Paper loop: review <N> papers (<date range>)`. In the description:

- List every paper reviewed this run with its decision (adopt/defer/reject) and a one-line reason.
- For anything adopted: name the new ADR, the files changed, and the tests added.
- Report the `pytest` result (pass count) and the `eval/harness.py` recall@k score, and note any change from `eval/BASELINE.md`'s prior value.

**Never push directly to the default branch.** This repository's entire
philosophy (see ADR 0002 and the README) is that autonomy is only safe with
an evaluation gate and a human in the loop - the PR review is that gate for
this loop specifically. If anything in this run is ambiguous enough that
you're not confident in the adopt/defer decision, say so plainly in the PR
description rather than guessing.
