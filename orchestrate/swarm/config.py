"""Typed configuration for the swarm: roles, tasks, budget, and window.

The on-disk source of truth is `orchestrate/swarm.yml`. This module turns it
into frozen dataclasses and validates internal consistency (every task
references defined roles, exactly one executor role can write, etc.) so that
a malformed registry fails loudly at load time rather than mid-run on a cloud
VM. Loading is the only place `pyyaml` is touched; everything downstream
works on the typed objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


class ConfigError(ValueError):
    """Raised when swarm.yml is missing required fields or is inconsistent."""


@dataclass(frozen=True)
class RoleConfig:
    """One agent role. `can_write`/`auto_create_pr` gate side effects."""

    name: str
    model: str
    prompt_file: str
    can_write: bool = False
    auto_create_pr: bool = False
    timeout_seconds: int = 3600
    max_retries: int = 2

    def __post_init__(self) -> None:
        if self.auto_create_pr and not self.can_write:
            raise ConfigError(
                f"role '{self.name}': auto_create_pr requires can_write=true"
            )
        if self.timeout_seconds <= 0:
            raise ConfigError(f"role '{self.name}': timeout_seconds must be > 0")
        if self.max_retries < 0:
            raise ConfigError(f"role '{self.name}': max_retries must be >= 0")


@dataclass(frozen=True)
class BudgetConfig:
    """Hard cost/parallelism caps enforced by the orchestrator."""

    max_parallel_thinkers: int = 3
    max_code_changing_tasks_per_run: int = 1
    max_total_runs_per_cycle: int = 12
    # Soft daily ceiling for local loop mode (cap, not a quota to pad toward).
    daily_commit_ceiling: int = 40
    # Soft per-cycle commit hint for the local executor prompt.
    max_commits_per_cycle: int = 5

    def __post_init__(self) -> None:
        if self.max_parallel_thinkers < 1:
            raise ConfigError("budget.max_parallel_thinkers must be >= 1")
        if self.max_code_changing_tasks_per_run < 0:
            raise ConfigError("budget.max_code_changing_tasks_per_run must be >= 0")
        if self.max_total_runs_per_cycle < 1:
            raise ConfigError("budget.max_total_runs_per_cycle must be >= 1")
        if self.daily_commit_ceiling < 1:
            raise ConfigError("budget.daily_commit_ceiling must be >= 1")
        if self.max_commits_per_cycle < 1:
            raise ConfigError("budget.max_commits_per_cycle must be >= 1")


@dataclass(frozen=True)
class ReleaseConfig:
    """When the local loop should cut a version bump on main."""

    weekday: str = "Friday"  # Python calendar day name, e.g. Friday

    def __post_init__(self) -> None:
        valid = {
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        }
        if self.weekday not in valid:
            raise ConfigError(
                f"release.weekday must be one of {sorted(valid)}, got {self.weekday!r}"
            )


@dataclass(frozen=True)
class TaskConfig:
    """A unit of meaningful work the swarm can pick up on a given day."""

    name: str
    description: str
    repo: str
    priority: int = 100
    thinker_roles: List[str] = field(default_factory=list)
    judge_role: Optional[str] = None
    executor_role: Optional[str] = None
    verifier_role: Optional[str] = None
    enabled: bool = True


@dataclass(frozen=True)
class WindowConfig:
    """The daily operating window; the orchestrator stops issuing new work
    at `end` and cancels anything still running past a grace period."""

    timezone: str = "Asia/Kolkata"
    start: str = "04:00"
    end: str = "09:00"


@dataclass(frozen=True)
class SwarmConfig:
    window: WindowConfig
    budget: BudgetConfig
    roles: Dict[str, RoleConfig]
    tasks: List[TaskConfig]
    release: ReleaseConfig = field(default_factory=ReleaseConfig)

    def enabled_tasks(self) -> List[TaskConfig]:
        """Enabled tasks, highest priority first (lower number = higher)."""
        return sorted(
            (t for t in self.tasks if t.enabled), key=lambda t: (t.priority, t.name)
        )

    def required_model_ids(self) -> List[str]:
        """Distinct model ids referenced by any role (for pre-flight check)."""
        return sorted({role.model for role in self.roles.values()})

    def get_task(self, name: str) -> TaskConfig:
        for task in self.tasks:
            if task.name == name:
                return task
        raise ConfigError(f"no task named '{name}' in swarm config")

    def _referenced_roles(self, task: TaskConfig) -> List[str]:
        refs = list(task.thinker_roles)
        for single in (task.judge_role, task.executor_role, task.verifier_role):
            if single:
                refs.append(single)
        return refs

    def validate(self) -> None:
        """Cross-object consistency checks (run once at load time)."""
        if not self.roles:
            raise ConfigError("swarm config defines no roles")
        if not self.tasks:
            raise ConfigError("swarm config defines no tasks")

        names = [t.name for t in self.tasks]
        if len(names) != len(set(names)):
            raise ConfigError("duplicate task names in swarm config")

        for task in self.tasks:
            for role_name in self._referenced_roles(task):
                if role_name not in self.roles:
                    raise ConfigError(
                        f"task '{task.name}' references undefined role '{role_name}'"
                    )
            if task.executor_role is not None:
                executor = self.roles[task.executor_role]
                if not executor.can_write:
                    raise ConfigError(
                        f"task '{task.name}': executor role '{executor.name}' "
                        "must have can_write=true"
                    )
            # Thinkers, judges, and verifiers must never be able to write.
            for read_only_role in task.thinker_roles + [
                r for r in (task.judge_role, task.verifier_role) if r
            ]:
                if self.roles[read_only_role].can_write:
                    raise ConfigError(
                        f"task '{task.name}': role '{read_only_role}' is used in a "
                        "read-only slot (thinker/judge/verifier) but has "
                        "can_write=true"
                    )


def _require(mapping: dict, key: str, context: str):
    if key not in mapping:
        raise ConfigError(f"{context}: missing required key '{key}'")
    return mapping[key]


def parse_config(data: dict) -> SwarmConfig:
    """Build a validated `SwarmConfig` from an already-parsed mapping.

    Pure and yaml-free so it can be unit-tested with plain dicts.
    """
    if not isinstance(data, dict):
        raise ConfigError("swarm config root must be a mapping")

    window_raw = data.get("window", {}) or {}
    window = WindowConfig(
        timezone=window_raw.get("timezone", "Asia/Kolkata"),
        start=window_raw.get("start", "04:00"),
        end=window_raw.get("end", "09:00"),
    )

    budget_raw = data.get("budget", {}) or {}
    budget = BudgetConfig(
        max_parallel_thinkers=int(budget_raw.get("max_parallel_thinkers", 3)),
        max_code_changing_tasks_per_run=int(
            budget_raw.get("max_code_changing_tasks_per_run", 1)
        ),
        max_total_runs_per_cycle=int(budget_raw.get("max_total_runs_per_cycle", 12)),
        daily_commit_ceiling=int(budget_raw.get("daily_commit_ceiling", 40)),
        max_commits_per_cycle=int(budget_raw.get("max_commits_per_cycle", 5)),
    )

    release_raw = data.get("release", {}) or {}
    release = ReleaseConfig(weekday=str(release_raw.get("weekday", "Friday")))

    roles_raw = _require(data, "roles", "swarm config")
    if not isinstance(roles_raw, dict):
        raise ConfigError("'roles' must be a mapping of name -> role")
    roles: Dict[str, RoleConfig] = {}
    for name, role_data in roles_raw.items():
        role_data = role_data or {}
        roles[name] = RoleConfig(
            name=name,
            model=_require(role_data, "model", f"role '{name}'"),
            prompt_file=_require(role_data, "prompt_file", f"role '{name}'"),
            can_write=bool(role_data.get("can_write", False)),
            auto_create_pr=bool(role_data.get("auto_create_pr", False)),
            timeout_seconds=int(role_data.get("timeout_seconds", 3600)),
            max_retries=int(role_data.get("max_retries", 2)),
        )

    tasks_raw = _require(data, "tasks", "swarm config")
    if not isinstance(tasks_raw, list):
        raise ConfigError("'tasks' must be a list")
    tasks: List[TaskConfig] = []
    for task_data in tasks_raw:
        task_data = task_data or {}
        tasks.append(
            TaskConfig(
                name=_require(task_data, "name", "task"),
                description=_require(task_data, "description", "task"),
                repo=_require(task_data, "repo", "task"),
                priority=int(task_data.get("priority", 100)),
                thinker_roles=list(task_data.get("thinker_roles", [])),
                judge_role=task_data.get("judge_role"),
                executor_role=task_data.get("executor_role"),
                verifier_role=task_data.get("verifier_role"),
                enabled=bool(task_data.get("enabled", True)),
            )
        )

    config = SwarmConfig(
        window=window, budget=budget, roles=roles, tasks=tasks, release=release
    )
    config.validate()
    return config


def load_config(path: Path) -> SwarmConfig:
    """Load and validate `swarm.yml` from disk (requires the orchestrate extra)."""
    import yaml

    with open(path) as f:
        data = yaml.safe_load(f) or {}
    return parse_config(data)
