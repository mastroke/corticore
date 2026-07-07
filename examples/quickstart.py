#!/usr/bin/env python3
"""The 60-second corticore quickstart. Run with: python examples/quickstart.py"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from corticore import Memory  # noqa: E402


def main() -> None:
    db_path = Path(tempfile.mkdtemp()) / "quickstart.db"
    print(f"Opening a zero-setup memory at {db_path} (just a SQLite file)\n")

    with Memory(str(db_path)) as mem:
        print("remember() three facts, including a name correction...")
        mem.remember("The user's name is Priya.")
        mem.remember("Priya prefers dark mode.")
        name_correction_id = mem.remember("The user's name is actually Priyanka, not Priya.")

        print("\nreflect() to consolidate: resolve the name conflict...")
        report = mem.reflect()
        print(
            f"  merged={len(report.merged)} superseded={len(report.superseded)} "
            f"pruned={len(report.pruned)}"
        )

        print("\nrecall(\"what is the user's name?\")...")
        results = mem.recall("what is the user's name?")
        for r in results:
            print(f"  [{r.score:.3f}] {r.text}")

        print(f"\nwhy({name_correction_id[:8]}...) — full history for the winning fact:")
        trace = mem.why(name_correction_id)
        print(trace)


if __name__ == "__main__":
    main()
