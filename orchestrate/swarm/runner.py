"""The Cursor Cloud boundary: launching, resuming, and observing role runs.

`SwarmRunner` owns everything side-effecting about talking to cloud agents -
retries with backoff on retryable startup failures, deadline enforcement, and
turning a finished run into a parsed `RoleOutcome`. It talks to a
`CloudClient` protocol, never to the SDK directly, so tests inject a fake
client and the base suite needs neither the SDK nor a network.

Two failure modes are kept distinct (mirroring the SDK skill's guidance):
a startup failure means the run never executed (retry the environment); a
terminal `error`/`cancelled` status means it ran and failed (don't retry
blindly - surface it).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Optional, Protocol

from .config import RoleConfig
from .results import AgentResult, MalformedResultError, parse_agent_result

STATUS_FINISHED = "finished"
STATUS_ERROR = "error"
STATUS_CANCELLED = "cancelled"


class CloudStartupError(RuntimeError):
    """The run never executed (auth/config/network). Carries retryability."""

    def __init__(self, message: str, is_retryable: bool = False) -> None:
        super().__init__(message)
        self.message = message
        self.is_retryable = is_retryable


@dataclass(frozen=True)
class CloudRunResult:
    """The raw outcome of one cloud run, before result-block parsing."""

    agent_id: str
    run_id: str
    status: str
    text: str = ""
    pr_url: Optional[str] = None


class CloudClient(Protocol):
    """Minimal seam over the Cursor SDK. Implemented by `CursorCloudClient`."""

    def run(
        self,
        prompt: str,
        model: str,
        repo: Optional[str],
        auto_create_pr: bool,
        timeout_seconds: int,
    ) -> CloudRunResult: ...

    def resume(
        self,
        agent_id: str,
        prompt: str,
        timeout_seconds: int,
    ) -> CloudRunResult: ...


@dataclass
class RoleOutcome:
    """The orchestrator-facing result of running one role once."""

    role: str
    status: str
    agent_id: Optional[str] = None
    run_id: Optional[str] = None
    result: Optional[AgentResult] = None
    pr_url: Optional[str] = None
    error: Optional[str] = None
    attempts: int = 0
    extra: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == STATUS_FINISHED and self.result is not None


class SwarmRunner:
    """Runs roles against a `CloudClient` with retries and a hard deadline."""

    def __init__(
        self,
        client: CloudClient,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        base_backoff_seconds: float = 5.0,
    ) -> None:
        self._client = client
        self._clock = clock
        self._sleep = sleep
        self._base_backoff = base_backoff_seconds

    def _remaining(self, deadline: Optional[float]) -> Optional[float]:
        if deadline is None:
            return None
        return deadline - self._clock()

    def run_role(
        self,
        role: RoleConfig,
        prompt: str,
        repo: Optional[str],
        *,
        deadline: Optional[float] = None,
        resume_agent_id: Optional[str] = None,
    ) -> RoleOutcome:
        """Run (or resume) one role, retrying only retryable startup failures.

        `deadline` is an absolute value on the same scale as `clock` (e.g.
        `time.monotonic()`); when reached, no new attempt is started and the
        outcome is reported as cancelled.
        """
        attempts = 0
        last_error: Optional[str] = None

        while attempts <= role.max_retries:
            remaining = self._remaining(deadline)
            if remaining is not None and remaining <= 0:
                return RoleOutcome(
                    role=role.name,
                    status=STATUS_CANCELLED,
                    error="deadline reached before run could start",
                    attempts=attempts,
                )

            timeout = role.timeout_seconds
            if remaining is not None:
                timeout = int(min(timeout, max(1, remaining)))

            attempts += 1
            try:
                if resume_agent_id:
                    raw = self._client.resume(resume_agent_id, prompt, timeout)
                else:
                    raw = self._client.run(
                        prompt,
                        role.model,
                        repo,
                        role.auto_create_pr,
                        timeout,
                    )
            except CloudStartupError as exc:
                last_error = f"startup failed: {exc.message} (retryable={exc.is_retryable})"
                if not exc.is_retryable or attempts > role.max_retries:
                    return RoleOutcome(
                        role=role.name,
                        status=STATUS_ERROR,
                        error=last_error,
                        attempts=attempts,
                    )
                backoff = self._base_backoff * (2 ** (attempts - 1))
                remaining = self._remaining(deadline)
                if remaining is not None and backoff >= remaining:
                    return RoleOutcome(
                        role=role.name,
                        status=STATUS_CANCELLED,
                        error=f"{last_error}; no time left to retry before deadline",
                        attempts=attempts,
                    )
                self._sleep(backoff)
                continue

            return self._finalize(role, raw, attempts)

        return RoleOutcome(
            role=role.name,
            status=STATUS_ERROR,
            error=last_error or "exhausted retries",
            attempts=attempts,
        )

    def _finalize(
        self, role: RoleConfig, raw: CloudRunResult, attempts: int
    ) -> RoleOutcome:
        if raw.status != STATUS_FINISHED:
            return RoleOutcome(
                role=role.name,
                status=raw.status or STATUS_ERROR,
                agent_id=raw.agent_id,
                run_id=raw.run_id,
                pr_url=raw.pr_url,
                error=f"run ended with status={raw.status!r}",
                attempts=attempts,
            )

        try:
            parsed = parse_agent_result(raw.text)
        except MalformedResultError as exc:
            # A finished run with an unparseable result is treated as failed:
            # a confused agent must never be mistaken for a passing one.
            return RoleOutcome(
                role=role.name,
                status=STATUS_ERROR,
                agent_id=raw.agent_id,
                run_id=raw.run_id,
                pr_url=raw.pr_url,
                error=f"malformed result: {exc}",
                attempts=attempts,
            )

        return RoleOutcome(
            role=role.name,
            status=STATUS_FINISHED,
            agent_id=raw.agent_id,
            run_id=raw.run_id,
            result=parsed,
            pr_url=raw.pr_url,
            attempts=attempts,
        )
