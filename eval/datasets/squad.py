"""Load a real Hugging Face dataset (SQuAD) into the harness `Dataset` shape.

SQuAD (`rajpurkar/squad`) is reading-comprehension data: each row has a
`context` paragraph, a `question`, and one or more gold `answers` spans taken
verbatim from the context. That maps cleanly onto corticore's memory-recall
eval:

- **facts**  — every context is split into sentences; each sentence becomes a
  stored memory. Sentences from many paragraphs live in one store together, so
  the correct answer sentence has to be retrieved among real distractors.
- **queries** — each question is a recall query, expecting the gold answer
  span to appear in a top-k recalled memory.

This keeps the exact `(facts, queries, expects_substring)` contract the
built-in synthetic dataset uses, so it drops straight into `harness.run()`.

Requires the optional `hf` extra (`pip install corticore[hf]`, which installs
`datasets`). The first load downloads from the Hugging Face Hub and is cached
locally; later runs are offline.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Import the harness contract (Dataset/Query) without turning eval/ into a
# package. Mirrors how benchmark_embedders.py imports from harness.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness import Dataset, Query  # noqa: E402

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


def _split_sentences(text: str) -> list[str]:
    """A dependency-free sentence splitter good enough for SQuAD contexts."""
    return [s.strip() for s in _SENTENCE_BOUNDARY.split(text.strip()) if s.strip()]


def load_squad(
    limit: int = 100,
    split: str = "validation",
    dataset_name: str = "rajpurkar/squad",
    require_answerable: bool = True,
    seed: int = 42,
) -> Dataset:
    """Load `limit` SQuAD rows into a harness `Dataset`.

    The split is shuffled with a fixed `seed` before slicing. SQuAD is ordered
    by source article, so a raw `[:limit]` slice would draw from only a handful
    of paragraphs; shuffling spreads the sample across many articles, giving a
    realistic pool of distractor memories to retrieve against.

    `require_answerable=True` (default) keeps only questions whose gold answer
    span survives sentence-splitting into some stored fact, so the score
    measures corticore's retrieval among distractors rather than penalizing
    the sentence splitter for spans it happened to break. Set it to `False` to
    keep every question.
    """
    try:
        from datasets import load_dataset
    except ImportError as exc:  # pragma: no cover - exercised via the extra
        raise ImportError(
            "Loading SQuAD needs the 'hf' extra: pip install corticore[hf]"
        ) from exc

    full = load_dataset(dataset_name, split=split)
    n = min(limit, len(full))
    rows = list(full.shuffle(seed=seed).select(range(n)))

    facts: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for sentence in _split_sentences(row["context"]):
            if sentence not in seen:
                seen.add(sentence)
                facts.append(sentence)

    lowered_facts = [f.lower() for f in facts]
    queries: list[Query] = []
    kept, total = 0, 0
    for row in rows:
        answer_texts = row["answers"]["text"]
        if not answer_texts:
            continue
        total += 1
        answer = answer_texts[0]
        if require_answerable and not any(
            answer.lower() in f for f in lowered_facts
        ):
            continue
        kept += 1
        queries.append(Query(row["question"], answer))

    suffix = f" (answerable {kept}/{total})" if require_answerable else ""
    return Dataset(
        name=f"squad:{split}[:{limit}]{suffix}",
        facts=facts,
        queries=queries,
    )
