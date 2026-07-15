# Eval baseline

The last known-good score from `eval/harness.py`, checked in (not gitignored,
unlike `eval/results/`) so the paper-loop orchestration has something
concrete to regress against.

| Date       | Dataset        | recall@k       | Score | Notes                                                                                          |
| ---------- | -------------- | -------------- | ----- | ------------------------------------------------------------------------------------------------ |
| 2026-07-06 | synthetic-v0   | recall@3 = 4/5 | 80%   | Baseline at depth-round completion. Known gap: the default `LocalEmbedder` (lexical hashing) misses the paraphrase-only query ("what theme does the user prefer?" vs. "dark mode"); `sentence-transformers`/Azure OpenAI embedders are expected to close this but haven't been benchmarked here yet. |
| 2026-07-15 | synthetic-v0   | recall@3 = 4/5 | 80%   | Default `LocalEmbedder`, re-confirmed via `eval/benchmark_embedders.py` (F004). Unchanged; this is the dependency-free baseline. |
| 2026-07-15 | synthetic-v0   | recall@3 = 5/5 | 100%  | `SentenceTransformerEmbedder(all-MiniLM-L6-v2)` via `pip install corticore[st]`, measured by `eval/benchmark_embedders.py` (F004). Closes the paraphrase-only gap ("theme" vs "dark mode") that lexical hashing misses, at ~0.57s vs ~0.01s per run and a heavy torch/transformers dependency. Semantic embeddings are the recommended upgrade when recall quality matters more than zero-setup. |

## Rule

Every paper-loop run (see [`research/design/adr/0005-scheduled-cloud-agent-research-loop.md`](../research/design/adr/0005-scheduled-cloud-agent-research-loop.md))
must run `python eval/harness.py` and compare against the score above before
opening its PR:

- **Same or better** - update the table above with the new score, date, and a
  one-line note of what changed.
- **Worse** - fix the regression before opening the PR, or, only if the
  regression is an intentional, understood tradeoff, say so explicitly here
  and in the PR description. Never let a regression pass silently.
