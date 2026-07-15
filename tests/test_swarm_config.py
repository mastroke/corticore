"""Tests for swarm config parsing and consistency validation (pure)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestrate"))

from swarm.config import ConfigError, parse_config  # noqa: E402


def _valid_data():
    return {
        "window": {"timezone": "Asia/Kolkata", "start": "04:00", "end": "09:00"},
        "budget": {"max_parallel_thinkers": 3, "max_code_changing_tasks_per_run": 1},
        "roles": {
            "scout": {"model": "gpt-5.6-sol", "prompt_file": "s.md"},
            "judge": {"model": "gpt-5.6-sol", "prompt_file": "j.md"},
            "executor": {
                "model": "composer-2.5",
                "prompt_file": "e.md",
                "can_write": True,
                "auto_create_pr": True,
            },
        },
        "tasks": [
            {
                "name": "t1",
                "description": "d",
                "repo": "o/r",
                "priority": 10,
                "thinker_roles": ["scout"],
                "judge_role": "judge",
                "executor_role": "executor",
            }
        ],
    }


def test_parse_valid_config():
    config = parse_config(_valid_data())
    assert config.required_model_ids() == ["composer-2.5", "gpt-5.6-sol"]
    assert config.get_task("t1").repo == "o/r"
    assert config.enabled_tasks()[0].name == "t1"


def test_enabled_tasks_sorted_by_priority():
    data = _valid_data()
    data["tasks"].append(
        {
            "name": "t0",
            "description": "d",
            "repo": "o/r",
            "priority": 5,
            "thinker_roles": ["scout"],
        }
    )
    config = parse_config(data)
    assert [t.name for t in config.enabled_tasks()] == ["t0", "t1"]


def test_executor_must_be_writable():
    data = _valid_data()
    data["roles"]["executor"]["can_write"] = False
    data["roles"]["executor"]["auto_create_pr"] = False
    with pytest.raises(ConfigError, match="must have can_write"):
        parse_config(data)


def test_auto_create_pr_requires_can_write():
    data = _valid_data()
    data["roles"]["scout"]["auto_create_pr"] = True
    with pytest.raises(ConfigError, match="auto_create_pr requires can_write"):
        parse_config(data)


def test_thinker_cannot_be_writable():
    data = _valid_data()
    data["roles"]["scout"]["can_write"] = True
    with pytest.raises(ConfigError, match="read-only slot"):
        parse_config(data)


def test_task_referencing_unknown_role_fails():
    data = _valid_data()
    data["tasks"][0]["thinker_roles"] = ["ghost"]
    with pytest.raises(ConfigError, match="undefined role 'ghost'"):
        parse_config(data)


def test_duplicate_task_names_fail():
    data = _valid_data()
    data["tasks"].append(dict(data["tasks"][0]))
    with pytest.raises(ConfigError, match="duplicate task names"):
        parse_config(data)


def test_missing_roles_key_fails():
    data = _valid_data()
    del data["roles"]
    with pytest.raises(ConfigError, match="missing required key 'roles'"):
        parse_config(data)


def test_real_swarm_yml_loads_and_validates():
    yaml = pytest.importorskip("yaml")  # part of the orchestrate extra
    path = REPO_ROOT / "orchestrate" / "swarm.yml"
    data = yaml.safe_load(path.read_text())
    config = parse_config(data)
    task = config.get_task("corticore-maintenance")
    assert task.executor_role == "executor"
    assert config.roles["executor"].can_write is True
    assert config.roles["maintenance_scout"].can_write is False
