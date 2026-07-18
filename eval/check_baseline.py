#!/usr/bin/env python3
"""Fail the build if `eval/harness.py`'s recall@k regresses below the baseline.

`eval/harness.py` runs with the *default* zero-setup `LocalEmbedder`, so the
gate must compare against the best score recorded for that same default path.
`eval/BASELINE.md` also records scores for optional, heavier embedders (e.g.
`SentenceTransformerEmbedder`, which hits 100% but needs `corticore[st]`);
those rows must NOT become the floor, or the gate would demand a score the
dependency-free CI environment can never reach. So we take the highest score
among rows that are not tagged with an alternative-embedder marker.

This turns the "never let a regression pass silently" rule - previously
enforced only by a prompt - into a hard, deterministic CI gate.

Usage:
    python eval/check_baseline.py [--baseline eval/BASELINE.md]

Exit codes: 0 = same-or-better, 1 = regression (or baseline unreadable).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Optional

EVAL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EVAL_DIR))

DEFAULT_BASELINE = EVAL_DIR / "BASELINE.md"
_PERCENT_RE = re.compile(r"(\d{1,3})%")

# Concrete markers that a baseline row was measured with a non-default embedder
# (matched against the de-spaced, lower-cased row). Prose like
# "sentence-transformers are expected to help" is intentionally NOT matched -
# only rows that name the embedder class or the extra used to run it.
_ALT_EMBEDDER_MARKERS = (
    "sentencetransformerembedder",
    "azureopenaiembedder",
    "corticore[st]",
)


def parse_baseline_score(baseline_text: str) -> Optional[float]:
    """Return the highest percentage in the baseline file as a 0..1 fraction.

    Pure and unit-tested (see tests/test_check_baseline.py). Returns None when
    the file records no percentage - the caller decides how to treat that.
    """
    scores = [int(m.group(1)) for m in _PERCENT_RE.finditer(baseline_text)]
    scores = [s for s in scores if 0 <= s <= 100]
    if not scores:
        return None
    return max(scores) / 100.0


def parse_default_embedder_baseline(baseline_text: str) -> Optional[float]:
    """Highest baseline score achieved with the default embedder, as 0..1.

    Scans the markdown table rows and ignores any row tagged with an
    alternative-embedder marker (see `_ALT_EMBEDDER_MARKERS`), so the floor
    reflects what the default `LocalEmbedder` path in `eval/harness.py` can
    actually reach. Falls back to the overall max when no default-path row is
    found (keeps the gate strict rather than silently passing).
    """
    default_scores = []
    for line in baseline_text.splitlines():
        row = line.strip()
        if not row.startswith("|") or "%" not in row:
            continue
        collapsed = row.lower().replace(" ", "")
        if any(marker in collapsed for marker in _ALT_EMBEDDER_MARKERS):
            continue
        pcts = [int(m.group(1)) for m in _PERCENT_RE.finditer(row)]
        pcts = [p for p in pcts if 0 <= p <= 100]
        if pcts:
            default_scores.append(max(pcts))
    if not default_scores:
        return parse_baseline_score(baseline_text)
    return max(default_scores) / 100.0


def current_score() -> float:
    from harness import _synthetic_dataset, run  # local import; needs src on path

    result = run(_synthetic_dataset())
    return float(result["recall_at_k"]["score"])


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    args = parser.parse_args(argv)

    if not args.baseline.exists():
        print(f"baseline file not found: {args.baseline}", file=sys.stderr)
        return 1

    baseline = parse_default_embedder_baseline(args.baseline.read_text())
    if baseline is None:
        print("could not parse any score from the baseline file", file=sys.stderr)
        return 1

    score = current_score()
    # Small tolerance for float formatting; a true regression is < baseline.
    if score + 1e-9 < baseline:
        print(
            f"[eval gate] REGRESSION: recall@k {score:.0%} < baseline {baseline:.0%}. "
            "Fix it, or update eval/BASELINE.md with a justified tradeoff.",
            file=sys.stderr,
        )
        return 1

    print(f"[eval gate] OK: recall@k {score:.0%} >= baseline {baseline:.0%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
