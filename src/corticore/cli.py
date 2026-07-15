"""`corticore` command-line tool for inspecting a memory store (F010).

A thin, read-mostly wrapper over the `Memory` API for operators and debugging:

    corticore --db agent.db list
    corticore --db agent.db recall "what is the user's name?"
    corticore --db agent.db why <memory_id>
    corticore --db agent.db reflect

The default database is `corticore.db`, matching the library default.
"""

from __future__ import annotations

import argparse
import sys
from typing import Optional, Sequence

from corticore.core.memory import Memory


def _truncate(text: str, width: int = 70) -> str:
    text = text.replace("\n", " ")
    return text if len(text) <= width else text[: width - 1] + "\u2026"


def cmd_list(mem: Memory, args: argparse.Namespace) -> int:
    """Print stored memories, most salient first."""
    items = mem.store.all()
    if args.namespace is not None:
        items = [i for i in items if i.namespace == args.namespace]
    items.sort(key=lambda i: i.salience, reverse=True)
    items = items[: args.limit]

    if not items:
        print("(no memories)")
        return 0

    for item in items:
        print(
            f"{item.id[:8]}  ns={item.namespace:<10} "
            f"sal={item.salience:4.2f}  {item.status.value:<10} "
            f"{_truncate(item.text)}"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="corticore", description="Inspect a corticore memory store."
    )
    parser.add_argument(
        "--db",
        default="corticore.db",
        help="path to the SQLite memory database (default: corticore.db)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="list stored memories")
    p_list.add_argument("--namespace", default=None, help="only this namespace")
    p_list.add_argument("--limit", type=int, default=20, help="max rows (default: 20)")
    p_list.set_defaults(func=cmd_list)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    mem = Memory(args.db)
    try:
        return args.func(mem, args)
    finally:
        mem.close()


if __name__ == "__main__":
    raise SystemExit(main())
