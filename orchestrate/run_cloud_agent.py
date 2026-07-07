#!/usr/bin/env python3
"""Launch a Cursor cloud agent to run one paper-loop review cycle.

`build_prompt()` is pure and network-free (testable without the SDK or a
real API key - see `tests/test_run_cloud_agent.py`). `main()` does the one
real thing this script exists for: calling the Cursor SDK's one-shot
`Agent.prompt(...)` with `cloud=CloudAgentOptions(...)` so the review runs
on a Cursor-hosted VM against a fresh clone of the repo and opens a PR
(`auto_create_pr=True`) - it never pushes to the default branch directly.

Usage:
    python orchestrate/run_cloud_agent.py [--dry-run] [--papers-file PATH]
        [--repo mastroke/corticore] [--model composer-2.5]

Requires `CURSOR_API_KEY` in the environment (unless --dry-run). Requires
the `orchestrate` extra: pip install -e ".[orchestrate]"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

ORCHESTRATE_DIR = Path(__file__).resolve().parent
DEFAULT_PAPERS_FILE = ORCHESTRATE_DIR / ".new_papers.json"
DEFAULT_INSTRUCTIONS = ORCHESTRATE_DIR / "prompts" / "paper_loop_instructions.md"
DEFAULT_REPO = "mastroke/corticore"
DEFAULT_MODEL = "composer-2.5"


def build_prompt(new_papers: list[dict], instructions_path: Path) -> str:
    """Combine the versioned playbook with this run's new-papers list."""
    instructions = instructions_path.read_text()
    papers_block = json.dumps(new_papers, indent=2)
    return (
        f"{instructions}\n\n"
        "## New papers JSON for this run\n\n"
        f"```json\n{papers_block}\n```\n"
    )


def _load_new_papers(papers_file: Path) -> list[dict]:
    if not papers_file.exists():
        return []
    return json.loads(papers_file.read_text())


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--papers-file", type=Path, default=DEFAULT_PAPERS_FILE)
    parser.add_argument("--instructions", type=Path, default=DEFAULT_INSTRUCTIONS)
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the prompt that would be sent, without calling the Cursor SDK.",
    )
    args = parser.parse_args(argv)

    new_papers = _load_new_papers(args.papers_file)
    if not new_papers:
        print("No new papers to review this run - nothing to do.")
        return 0

    prompt = build_prompt(new_papers, args.instructions)

    if args.dry_run:
        print(prompt)
        print(f"\n[dry-run] would launch a cloud agent against {args.repo} "
              f"(model={args.model}) reviewing {len(new_papers)} paper(s).")
        return 0

    api_key = os.environ.get("CURSOR_API_KEY")
    if not api_key:
        print(
            "CURSOR_API_KEY is not set. Set it in the environment (in GitHub "
            "Actions: add it as a repository secret) or use --dry-run to "
            "preview the prompt without launching an agent.",
            file=sys.stderr,
        )
        return 1

    try:
        from cursor_sdk import (
            Agent,
            AgentOptions,
            CloudAgentOptions,
            CursorAgentError,
        )
    except ImportError:
        print(
            "run_cloud_agent.py requires the 'cursor-sdk' package. "
            "Install it with: pip install -e '.[orchestrate]'",
            file=sys.stderr,
        )
        return 1

    try:
        result = Agent.prompt(
            prompt,
            AgentOptions(
                api_key=api_key,
                model=args.model,
                cloud=CloudAgentOptions(
                    repos=[args.repo],
                    auto_create_pr=True,
                    skip_reviewer_request=False,
                ),
            ),
        )
    except CursorAgentError as exc:
        # The run never executed: auth, config, or network. Fix environment, retry.
        print(
            f"startup failed: {exc.message}, retryable={exc.is_retryable}",
            file=sys.stderr,
        )
        return 1

    print(f"run id: {getattr(result, 'id', 'unknown')}")
    print(f"status: {result.status}")

    if result.status == "error":
        # The run started but failed mid-flight - inspect the dashboard for details.
        print("run started but failed - see the Cursor dashboard for the transcript.", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
