"""corticore agent swarm: a role-separated Cursor Cloud orchestration layer.

This package coordinates several Cursor cloud agents with distinct, narrow
roles - parallel "thinker" scouts, a plan judge, a single code-writing
executor, and an independent blind verifier - under hard safety limits (one
active run per role, a daily operating window, cost caps, and a fail-closed
release gate).

Design rule mirrored from the rest of `orchestrate/`: all decision logic is
pure and network-free (see `models`, `prompts`, `results`, `gates`,
`planning`), and every side-effecting boundary (the Cursor SDK, GitHub) sits
behind an injectable seam so the base test suite never needs a network, an
API key, or the SDK installed.
"""

from __future__ import annotations

# Bump when the swarm.yml schema or ledger format changes in a breaking way.
SWARM_SCHEMA_VERSION = 1

__all__ = ["SWARM_SCHEMA_VERSION"]
