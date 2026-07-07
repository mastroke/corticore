#!/usr/bin/env python3
"""Detect new papers in the Agent-Memory-Paper-List worth reviewing.

Pure, network-free logic lives in `parse_papers`/`filter_new` so it's fully
unit-testable (see `tests/test_check_new_papers.py`). `main()` does the one
network call (stdlib `urllib.request`, no extra dependency) plus reading
`research/papers.yaml` (via `pyyaml`, this script's only real dependency -
see the `orchestrate` extra in `pyproject.toml`).

Usage:
    python orchestrate/check_new_papers.py [--cutoff 2026-01] [--output-file PATH]

Writes a JSON list of new papers to `--output-file` (default
`orchestrate/.new_papers.json`, gitignored) and, when running inside GitHub
Actions, appends `has_new`/`count` to `$GITHUB_OUTPUT` for the workflow to
branch on.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PAPERS_YAML = REPO_ROOT / "research" / "papers.yaml"
DEFAULT_OUTPUT_FILE = Path(__file__).resolve().parent / ".new_papers.json"
DEFAULT_README_URL = (
    "https://raw.githubusercontent.com/Shichun-Liu/Agent-Memory-Paper-List/main/README.md"
)
# The project's original, deliberate scope decision (see the founding
# discussion and research/design/DESIGN.md), not a value derived at runtime -
# the paper list's pre-2026 backlog is out of scope by design.
DEFAULT_CUTOFF = "2026-01"

_ENTRY_RE = re.compile(r"^-\s*\[(\d{4})/(\d{2})\]\s+(.*)$")
_URL_RE = re.compile(r"\((https?://[^)\s]+)\)")
_ARXIV_ID_RE = re.compile(r"(\d{4}\.\d{4,5})")


def parse_papers(readme_text: str) -> list[dict]:
    """Parse `- [YYYY/MM] Title. [[paper](url)]`-style lines into records.

    Only entries whose URL resolves to an arXiv id (`arxiv.org/abs/XXXX.XXXXX`)
    are returned - that's the id scheme `research/papers.yaml` uses, so
    entries we can't identify that way (openreview, doi.org, aclanthology,
    ...) are intentionally skipped rather than guessing an id. Duplicate ids
    (the source list repeats some papers across taxonomy sections) are
    deduped, keeping the first occurrence.
    """
    seen: dict[str, dict] = {}
    for line in readme_text.splitlines():
        match = _ENTRY_RE.match(line.strip())
        if not match:
            continue
        year, month, rest = match.groups()
        date = f"{year}-{month}"

        url_match = _URL_RE.search(rest)
        if not url_match:
            continue
        url = url_match.group(1)

        arxiv_match = _ARXIV_ID_RE.search(url)
        if not arxiv_match:
            continue
        paper_id = arxiv_match.group(1)

        title = rest[: url_match.start()]
        title = re.sub(r"\[\[.*$", "", title).rstrip(" .")

        if paper_id not in seen:
            seen[paper_id] = {"id": paper_id, "title": title, "date": date, "url": url}

    return list(seen.values())


def filter_new(
    papers: list[dict], known_ids: set[str], cutoff: str = DEFAULT_CUTOFF
) -> list[dict]:
    """Keep only papers dated `cutoff` or later that aren't already tracked."""
    return [p for p in papers if p["date"] >= cutoff and p["id"] not in known_ids]


def _load_known_ids(papers_yaml_path: Path) -> set[str]:
    import yaml

    with open(papers_yaml_path) as f:
        entries = yaml.safe_load(f) or []
    return {str(entry["id"]) for entry in entries if "id" in entry}


def _fetch_readme(url: str) -> str:
    with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310 - fixed, trusted URL
        return response.read().decode("utf-8")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cutoff", default=DEFAULT_CUTOFF)
    parser.add_argument("--papers-yaml", type=Path, default=DEFAULT_PAPERS_YAML)
    parser.add_argument("--readme-url", default=DEFAULT_README_URL)
    parser.add_argument("--output-file", type=Path, default=DEFAULT_OUTPUT_FILE)
    args = parser.parse_args(argv)

    readme_text = _fetch_readme(args.readme_url)
    known_ids = _load_known_ids(args.papers_yaml)
    all_papers = parse_papers(readme_text)
    new_papers = filter_new(all_papers, known_ids, cutoff=args.cutoff)
    on_or_after_cutoff = [p for p in all_papers if p["date"] >= args.cutoff]

    args.output_file.parent.mkdir(parents=True, exist_ok=True)
    args.output_file.write_text(json.dumps(new_papers, indent=2))

    summary = {
        "total_parsed": len(all_papers),
        "before_cutoff": len(all_papers) - len(on_or_after_cutoff),
        "on_or_after_cutoff_already_tracked": len(on_or_after_cutoff) - len(new_papers),
        "new": len(new_papers),
        "cutoff": args.cutoff,
        "new_papers": new_papers,
    }
    print(json.dumps(summary, indent=2))

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"has_new={'true' if new_papers else 'false'}\n")
            f.write(f"count={len(new_papers)}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
