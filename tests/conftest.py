"""Shared test fixtures/helpers for the swarm suite.

Puts `orchestrate/` on the import path (so `import swarm.*` works, mirroring
how the existing orchestrate tests import `check_new_papers`/`run_cloud_agent`)
and exposes a couple of small builders for the agent result contract and a
fake cloud client, so individual test modules stay focused.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
ORCHESTRATE_DIR = REPO_ROOT / "orchestrate"
if str(ORCHESTRATE_DIR) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATE_DIR))


def make_result_text(verdict: str, summary: str, data: Optional[dict] = None) -> str:
    """Build an agent reply containing a valid `<<<SWARM_RESULT>>>` block."""
    from swarm.prompts import RESULT_BEGIN, RESULT_END

    payload = {"verdict": verdict, "summary": summary, "data": data or {}}
    return (
        "Here is my analysis.\n\n"
        f"{RESULT_BEGIN}\n```json\n{json.dumps(payload)}\n```\n{RESULT_END}\n"
    )


class FakeCloudClient:
    """A `CloudClient` that returns canned replies keyed by the role name it
    finds embedded in the prompt's run-context JSON.

    `replies` maps role name -> CloudRunResult. `startup_errors` maps role
    name -> a list of exceptions to raise on successive attempts before
    finally returning the canned reply (to exercise retry/backoff).
    """

    def __init__(
        self,
        replies: Dict[str, "object"],
        startup_errors: Optional[Dict[str, List[Exception]]] = None,
    ) -> None:
        self.replies = replies
        self.startup_errors = startup_errors or {}
        self.calls: List[dict] = []
        self.resumed: List[str] = []

    @staticmethod
    def _role_from_prompt(prompt: str) -> str:
        # The run context JSON always carries "role": "<name>".
        marker = '"role": "'
        idx = prompt.find(marker)
        if idx == -1:
            return ""
        start = idx + len(marker)
        end = prompt.find('"', start)
        return prompt[start:end]

    def run(self, prompt, model, repo, auto_create_pr, timeout_seconds):
        role = self._role_from_prompt(prompt)
        self.calls.append(
            {"role": role, "model": model, "repo": repo, "auto_create_pr": auto_create_pr}
        )
        pending = self.startup_errors.get(role)
        if pending:
            raise pending.pop(0)
        return self.replies[role]

    def resume(self, agent_id, prompt, timeout_seconds):
        self.resumed.append(agent_id)
        role = self._role_from_prompt(prompt)
        return self.replies[role]


@pytest.fixture
def make_run_result():
    from swarm.runner import CloudRunResult

    def _build(role_text: str, status: str = "finished", agent_id="bc-x", pr_url=None):
        return CloudRunResult(
            agent_id=agent_id,
            run_id="run-1",
            status=status,
            text=role_text,
            pr_url=pr_url,
        )

    return _build
