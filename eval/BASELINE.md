# Eval baseline

The last known-good score from `eval/harness.py`, checked in (not gitignored,
unlike `eval/results/`) so the paper-loop orchestration has something
concrete to regress against.

| Date       | Dataset        | recall@k       | Score | Notes                                                                                          |
| ---------- | -------------- | -------------- | ----- | ------------------------------------------------------------------------------------------------ |
| 2026-07-06 | synthetic-v0   | recall@3 = 4/5 | 80%   | Baseline at depth-round completion. Known gap: the default `LocalEmbedder` (lexical hashing) misses the paraphrase-only query ("what theme does the user prefer?" vs. "dark mode"); `sentence-transformers`/Azure OpenAI embedders are expected to close this but haven't been benchmarked here yet. |

## Rule

Every paper-loop run (see [`research/design/adr/0005-scheduled-cloud-agent-research-loop.md`](../research/design/adr/0005-scheduled-cloud-agent-research-loop.md))
must run `python eval/harness.py` and compare against the score above before
opening its PR:

- **Same or better** - update the table above with the new score, date, and a
  one-line note of what changed.
- **Worse** - fix the regression before opening the PR, or, only if the
  regression is an intentional, understood tradeoff, say so explicitly here
  and in the PR description. Never let a regression pass silently.
