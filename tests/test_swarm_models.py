"""Tests for fail-closed model validation."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestrate"))

from swarm.models import ModelValidationError, validate_models  # noqa: E402


def test_validate_models_passes_when_all_present():
    validate_models(["gpt-5.6-sol", "composer-2.5"], ["composer-2.5", "gpt-5.6-sol", "auto"])


def test_validate_models_raises_on_missing_id():
    with pytest.raises(ModelValidationError, match="gpt-5.6-sol"):
        validate_models(["gpt-5.6-sol"], ["composer-2.5"])


def test_validate_models_lists_all_missing():
    with pytest.raises(ModelValidationError) as exc:
        validate_models(["a", "b"], ["c"])
    message = str(exc.value)
    assert "a" in message and "b" in message


def test_validate_models_empty_available_reported():
    with pytest.raises(ModelValidationError, match="none reported"):
        validate_models(["a"], [])
