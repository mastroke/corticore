"""Concrete `CloudClient` backed by the Cursor Python SDK.

Isolated from `runner.py` so importing the runner (and unit-testing it with a
fake client) never requires `cursor-sdk`. This adapter maps the SDK's
one-shot `Agent.prompt(...)` and `Agent.resume(...)` onto the swarm's
`CloudRunResult`, and translates a thrown `CursorAgentError` into the
runner's `CloudStartupError` so retry policy has the info it needs.
"""

from __future__ import annotations

from typing import Optional

from .runner import CloudRunResult, CloudStartupError


def repo_to_url(repo: str) -> str:
    """Normalize a repo reference into the full git URL the SDK expects.

    `cursor-sdk`'s `CloudRepository` is identified by a `url`, not by
    `owner/name`. Passing a bare `owner/name` string makes the SDK try
    `dict("owner/name")` and raise `ValueError: dictionary update sequence
    element #0 has length 1`. So we accept either an `owner/name` slug or an
    already-qualified URL and always hand the SDK a real URL.
    """
    repo = repo.strip()
    if repo.startswith("http://") or repo.startswith("https://") or repo.startswith("git@"):
        return repo
    return f"https://github.com/{repo}"


class CursorCloudClient:
    """Adapts `cursor_sdk.Agent` to the `CloudClient` protocol."""

    def __init__(self, api_key: str, *, skip_reviewer_request: bool = True) -> None:
        self._api_key = api_key
        self._skip_reviewer_request = skip_reviewer_request

    def _import_sdk(self):
        try:
            from cursor_sdk import (  # noqa: F401
                Agent,
                AgentOptions,
                CloudAgentOptions,
                CloudRepository,
                CursorAgentError,
            )
        except ImportError as exc:  # pragma: no cover - needs the extra
            raise CloudStartupError(
                "cursor-sdk is required to launch cloud agents. Install it with: "
                "pip install -e '.[orchestrate]'",
                is_retryable=False,
            ) from exc
        return Agent, AgentOptions, CloudAgentOptions, CloudRepository, CursorAgentError

    @staticmethod
    def _to_result(result) -> CloudRunResult:
        agent_id = str(getattr(result, "agent_id", "") or getattr(result, "id", "") or "")
        run_id = str(getattr(result, "id", "") or "")
        status = str(getattr(result, "status", "") or "")
        text = str(getattr(result, "result", "") or getattr(result, "text", "") or "")
        pr_url = getattr(result, "pr_url", None) or getattr(result, "prUrl", None)
        return CloudRunResult(
            agent_id=agent_id,
            run_id=run_id,
            status=status,
            text=text,
            pr_url=pr_url,
        )

    def run(
        self,
        prompt: str,
        model: str,
        repo: Optional[str],
        auto_create_pr: bool,
        timeout_seconds: int,
    ) -> CloudRunResult:
        Agent, AgentOptions, CloudAgentOptions, CloudRepository, CursorAgentError = (
            self._import_sdk()
        )
        repos = [CloudRepository(url=repo_to_url(repo))] if repo else []
        try:
            result = Agent.prompt(
                prompt,
                AgentOptions(
                    api_key=self._api_key,
                    model=model,
                    cloud=CloudAgentOptions(
                        repos=repos,
                        auto_create_pr=auto_create_pr,
                        skip_reviewer_request=self._skip_reviewer_request,
                    ),
                ),
            )
        except CursorAgentError as exc:
            raise CloudStartupError(
                getattr(exc, "message", str(exc)),
                is_retryable=bool(getattr(exc, "is_retryable", False)),
            ) from exc
        return self._to_result(result)

    def resume(
        self,
        agent_id: str,
        prompt: str,
        timeout_seconds: int,
    ) -> CloudRunResult:
        Agent, AgentOptions, _CloudAgentOptions, _CloudRepository, CursorAgentError = (
            self._import_sdk()
        )
        try:
            with Agent.resume(agent_id, AgentOptions(api_key=self._api_key)) as agent:
                run = agent.send(prompt)
                result = run.wait()
        except CursorAgentError as exc:
            raise CloudStartupError(
                getattr(exc, "message", str(exc)),
                is_retryable=bool(getattr(exc, "is_retryable", False)),
            ) from exc
        merged = self._to_result(result)
        # Resume keeps the original durable agent id.
        return CloudRunResult(
            agent_id=agent_id,
            run_id=merged.run_id,
            status=merged.status,
            text=merged.text,
            pr_url=merged.pr_url,
        )
