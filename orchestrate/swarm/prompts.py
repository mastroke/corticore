"""Prompt assembly: versioned markdown playbook + injected run context.

Same pattern as `orchestrate/run_cloud_agent.py:build_prompt` - the role's
instructions live in a reviewable, diffable markdown file under
`orchestrate/prompts/`, and this module appends a machine-readable context
block (task metadata, prior-role findings, the required output contract) at
run time. Keeping assembly pure means every prompt the swarm would send can
be inspected in a dry run and asserted on in tests without launching an agent.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

# Agents must terminate their reply with a fenced result block delimited by
# these sentinels. `results.parse_agent_result` looks for exactly this; the
# sentinels are embedded into every prompt so the contract is self-describing.
RESULT_BEGIN = "<<<SWARM_RESULT>>>"
RESULT_END = "<<<END_SWARM_RESULT>>>"


def load_prompt(prompt_file: str, prompts_dir: Path) -> str:
    """Read a role's markdown playbook from `prompts_dir/<prompt_file>`."""
    path = prompts_dir / prompt_file
    if not path.exists():
        raise FileNotFoundError(f"prompt file not found: {path}")
    return path.read_text()


def _result_contract(schema_hint: Optional[Dict[str, Any]]) -> str:
    example = schema_hint if schema_hint is not None else {
        "verdict": "one of the allowed verdicts for your role",
        "summary": "one-sentence human-readable summary",
        "data": {"role-specific": "fields"},
    }
    return (
        "## Required machine-readable result (mandatory)\n\n"
        "End your reply with exactly one fenced block in this form, and nothing "
        "after it:\n\n"
        f"{RESULT_BEGIN}\n"
        "```json\n"
        f"{json.dumps(example, indent=2)}\n"
        "```\n"
        f"{RESULT_END}\n\n"
        "The JSON must be valid and parseable. Do not add commentary after the "
        f"{RESULT_END} marker."
    )


def assemble_prompt(
    instructions: str,
    context: Dict[str, Any],
    schema_hint: Optional[Dict[str, Any]] = None,
) -> str:
    """Combine a role's instructions, this run's context, and the output contract.

    `context` is serialized to a JSON block (task, repo, upstream findings,
    deadlines). `schema_hint` optionally shows the exact result shape the role
    should emit.
    """
    context_block = json.dumps(context, indent=2, default=str)
    return (
        f"{instructions.rstrip()}\n\n"
        "## Run context (JSON)\n\n"
        f"```json\n{context_block}\n```\n\n"
        f"{_result_contract(schema_hint)}\n"
    )
