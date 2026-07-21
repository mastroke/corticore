"""Concrete Cursor SDK clients for cloud and local runtimes.

Isolated from `runner.py` so importing the runner (and unit-testing it with a
fake client) never requires `cursor-sdk`. These adapters map the SDK's
one-shot `Agent.prompt(...)` and `Agent.resume(...)` onto the swarm's
`CloudRunResult`, and translate a thrown `CursorAgentError` into the
runner's `CloudStartupError` so retry policy has the info it needs.

`CursorCloudClient` runs on Cursor-hosted VMs against a cloned repo.
`CursorLocalClient` runs on the caller's machine against a local `cwd`
(the dedicated swarm checkout). Use `build_client(runtime=...)` to pick.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

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


def _import_sdk():
    try:
        from cursor_sdk import (  # noqa: F401
            Agent,
            AgentOptions,
            CloudAgentOptions,
            CloudRepository,
            CursorAgentError,
            LocalAgentOptions,
        )
    except ImportError as exc:  # pragma: no cover - needs the extra
        raise CloudStartupError(
            "cursor-sdk is required to launch agents. Install it with: "
            "pip install -e '.[orchestrate]'",
            is_retryable=False,
        ) from exc
    return (
        Agent,
        AgentOptions,
        CloudAgentOptions,
        CloudRepository,
        LocalAgentOptions,
        CursorAgentError,
    )


class CursorCloudClient:
    """Adapts `cursor_sdk.Agent` (cloud runtime) to the `CloudClient` protocol."""

    runtime = "cloud"

    def __init__(self, api_key: str, *, skip_reviewer_request: bool = True) -> None:
        self._api_key = api_key
        self._skip_reviewer_request = skip_reviewer_request

    def run(
        self,
        prompt: str,
        model: str,
        repo: Optional[str],
        auto_create_pr: bool,
        timeout_seconds: int,
    ) -> CloudRunResult:
        Agent, AgentOptions, CloudAgentOptions, CloudRepository, _, CursorAgentError = (
            _import_sdk()
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
        return _to_result(result)

    def resume(
        self,
        agent_id: str,
        prompt: str,
        timeout_seconds: int,
    ) -> CloudRunResult:
        Agent, AgentOptions, _, _, _, CursorAgentError = _import_sdk()
        try:
            with Agent.resume(agent_id, AgentOptions(api_key=self._api_key)) as agent:
                run = agent.send(prompt)
                result = run.wait()
        except CursorAgentError as exc:
            raise CloudStartupError(
                getattr(exc, "message", str(exc)),
                is_retryable=bool(getattr(exc, "is_retryable", False)),
            ) from exc
        merged = _to_result(result)
        # Resume keeps the original durable agent id.
        return CloudRunResult(
            agent_id=agent_id,
            run_id=merged.run_id,
            status=merged.status,
            text=merged.text,
            pr_url=merged.pr_url,
        )


class CursorLocalClient:
    """Adapts `cursor_sdk.Agent` (local runtime) to the `CloudClient` protocol.

    Runs against `cwd` (the dedicated swarm checkout). `repo` and
    `auto_create_pr` are ignored - local mode edits the checkout and the
    orchestrator verifies + pushes; it never opens a PR via the SDK.
    """

    runtime = "local"

    def __init__(self, api_key: str, cwd: Union[str, Path]) -> None:
        self._api_key = api_key
        self._cwd = str(Path(cwd).resolve())

    def run(
        self,
        prompt: str,
        model: str,
        repo: Optional[str],
        auto_create_pr: bool,
        timeout_seconds: int,
    ) -> CloudRunResult:
        del repo, auto_create_pr  # not used in local mode
        Agent, AgentOptions, _, _, LocalAgentOptions, CursorAgentError = _import_sdk()
        try:
            result = Agent.prompt(
                prompt,
                AgentOptions(
                    api_key=self._api_key,
                    model=model,
                    local=LocalAgentOptions(cwd=self._cwd),
                ),
            )
        except CursorAgentError as exc:
            raise CloudStartupError(
                getattr(exc, "message", str(exc)),
                is_retryable=bool(getattr(exc, "is_retryable", False)),
            ) from exc
        return _to_result(result)

    def resume(
        self,
        agent_id: str,
        prompt: str,
        timeout_seconds: int,
    ) -> CloudRunResult:
        Agent, AgentOptions, _, _, _, CursorAgentError = _import_sdk()
        try:
            with Agent.resume(agent_id, AgentOptions(api_key=self._api_key)) as agent:
                run = agent.send(prompt)
                result = run.wait()
        except CursorAgentError as exc:
            raise CloudStartupError(
                getattr(exc, "message", str(exc)),
                is_retryable=bool(getattr(exc, "is_retryable", False)),
            ) from exc
        merged = _to_result(result)
        return CloudRunResult(
            agent_id=agent_id,
            run_id=merged.run_id,
            status=merged.status,
            text=merged.text,
            pr_url=merged.pr_url,
        )


def build_client(
    runtime: str,
    api_key: str,
    *,
    cwd: Optional[Union[str, Path]] = None,
    skip_reviewer_request: bool = True,
) -> Union[CursorCloudClient, CursorLocalClient]:
    """Factory: `runtime` is `cloud` or `local`."""
    if runtime == "cloud":
        return CursorCloudClient(
            api_key=api_key, skip_reviewer_request=skip_reviewer_request
        )
    if runtime == "local":
        if not cwd:
            raise CloudStartupError(
                "local runtime requires a checkout cwd", is_retryable=False
            )
        return CursorLocalClient(api_key=api_key, cwd=cwd)
    raise CloudStartupError(
        f"unknown runtime {runtime!r}; expected 'cloud' or 'local'",
        is_retryable=False,
    )
