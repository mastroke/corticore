# AGENTS.md

## Cursor Cloud specific instructions

corticore is a pure-Python library (no server, no GUI). Python 3.12 is used
here (`requires-python >=3.9`). The default path (`Memory("agent.db")`) is
zero-dependency and backed by a single SQLite file.

The update script provisions a `.venv` at the repo root and installs the
package editable with dev extras. Use that interpreter (`.venv/bin/python`)
for everything below.

Services / entry points:

- **Library API** — `from corticore import Memory` (`src/corticore/`).
- **CLI** — the `corticore` console script (`src/corticore/cli.py`);
  subcommands `list`, `recall`, `why`, `reflect` inspect an existing store.
  It has no `remember` subcommand, so populate a store via the library first.
  See the README "Command-line tool" section.
- **Eval harness** — `eval/harness.py` (see below).

Non-obvious caveats:

- **Eval harness needs `PYTHONPATH=src`**: run it as
  `PYTHONPATH=src .venv/bin/python eval/harness.py`. It is not exposed as a
  console script. Compare its `recall@3` against the last row of
  `eval/BASELINE.md` (baseline is 4/5 with the default lexical embedder).
- **8 tests skip by design**: the optional extras `st`
  (sentence-transformers), `openai`, `postgres`, and `orchestrate`
  (cursor-sdk/pyyaml) are not installed by the default dev setup, so their
  tests `skip`/`importorskip`. A green run is `67 passed, 8 skipped`. Install
  the matching extra (`.venv/bin/python -m pip install -e ".[st]"` etc.) only
  when working on that integration.
- **Postgres integration tests** (`tests/test_postgres_integration.py`) need
  Docker running or `CORTICORE_TEST_PG_DSN` set, plus the `postgres` extra;
  otherwise they skip.
- **No linter is configured** (no ruff/flake8/black config or dev dep despite
  the gitignored `.ruff_cache/`). CI (`.github/workflows/paper-loop.yml`) only
  runs pytest — there is no lint step to satisfy.
- **`feature-list.csv` is gitignored** and agent-local; the
  `corticore-feature-builder` skill references it but it may be absent.

Common commands (from repo root, after the update script has run):

- Tests: `.venv/bin/python -m pytest`
- Eval: `PYTHONPATH=src .venv/bin/python eval/harness.py`
- Quickstart demo: `.venv/bin/python examples/quickstart.py`
- CLI: `.venv/bin/corticore --db <path> list`
