# Taxonomy → corticore feature map

corticore tracks the unified taxonomy from
["Memory in the Age of AI Agents" (arXiv:2512.13564)](https://arxiv.org/abs/2512.13564),
which organizes agent memory along three axes:

- **Forms** — what carries the memory: Token-level (explicit/discrete),
  Parametric (model weights), Latent (hidden states).
- **Functions** — why the agent needs it: Factual (knowledge), Experiential
  (skills/insights), Working (active context management).
- **Dynamics** — how it changes over time: Formation, Evolution
  (consolidation/forgetting), Retrieval.

corticore v0.1 deliberately occupies a narrow, high-leverage slice of this
space rather than all of it — see [`design/DESIGN.md`](design/DESIGN.md) for
why. This table is the map from taxonomy cell to concrete module, kept
up to date as papers move from `unreviewed` to `adopted` in
[`papers.yaml`](papers.yaml).

| Axis | Cell | corticore module | Status |
| --- | --- | --- | --- |
| Forms | Token-level | all of `stores/`, `dynamics/` | implemented (v0.1) |
| Forms | Parametric | — | not planned for v0.1/v2 |
| Forms | Latent | — | not planned for v0.1/v2 |
| Functions | Factual | `remember()` + `dynamics/retrieval.py` | implemented (v0.1) |
| Functions | Experiential | — | candidate for v2 (see MemRL, 2601.03192) |
| Functions | Working | recency-boosted salience in `dynamics/decay.py` | partial (v0.1) |
| Dynamics | Formation | `Memory.remember()` | implemented (v0.1) |
| Dynamics | Evolution | `dynamics/decay.py`, `dynamics/consolidate.py` (access-decay + time-bounded expiry, ADR 0003) | implemented (v0.1), lead differentiator |
| Dynamics | Retrieval | `dynamics/retrieval.py` | implemented (v0.1, lexical+embedding hybrid) |

## Explicit non-goals (for now)

Per the reframe in the project's founding discussion: corticore does not
claim to replicate "every feature of the human brain." It claims a specific,
narrow, defensible position — zero-setup, forgetting-first, inspectable — and
expands only where a tracked paper and an ADR justify it.
