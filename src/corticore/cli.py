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


def cmd_recall(mem: Memory, args: argparse.Namespace) -> int:
    """Run a recall query and print the ranked, decay-adjusted results."""
    namespace = args.namespace or None  # empty string => search all namespaces
    results = mem.recall(args.query, k=args.k, namespace=namespace)
    if not results:
        print("(no results)")
        return 0
    for r in results:
        print(f"{r.score:6.3f}  {r.id[:8]}  {_truncate(r.text)}")
    return 0


def cmd_why(mem: Memory, args: argparse.Namespace) -> int:
    """Print the full trace (why a memory exists / how it changed)."""
    trace = mem.why(args.memory_id)
    if not trace.events:
        print(f"(no trace for {args.memory_id})")
        return 0
    for event in trace.events:
        print(f"{event.at:15.3f}  {event.kind:<10}  {event.detail}")
    return 0


def cmd_reflect(mem: Memory, args: argparse.Namespace) -> int:
    """Run a consolidation pass and report what changed."""
    report = mem.reflect()
    print(
        f"inspected={report.inspected} merged={len(report.merged)} "
        f"superseded={len(report.superseded)} pruned={len(report.pruned)}"
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

    p_recall = sub.add_parser("recall", help="run a recall query")
    p_recall.add_argument("query", help="the query text")
    p_recall.add_argument("--k", type=int, default=None, help="number of results")
    p_recall.add_argument(
        "--namespace",
        default="default",
        help="namespace to search (default: 'default'; use '' for all)",
    )
    p_recall.set_defaults(func=cmd_recall)

    p_why = sub.add_parser("why", help="show the trace behind a memory")
    p_why.add_argument("memory_id", help="the memory id to explain")
    p_why.set_defaults(func=cmd_why)

    p_reflect = sub.add_parser("reflect", help="run a consolidation pass")
    p_reflect.set_defaults(func=cmd_reflect)

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
