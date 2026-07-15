#!/usr/bin/env python3
"""Fail the build if `eval/harness.py`'s recall@k regresses below the baseline.

The baseline is the highest recorded score in `eval/BASELINE.md` (the same
file the paper loop and swarm executor keep up to date). This turns the
"never let a regression pass silently" rule - previously enforced only by a
prompt - into a hard, deterministic CI gate.

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

    baseline = parse_baseline_score(args.baseline.read_text())
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
