"""Tests for the SDK repo URL normalizer and client factory (no live SDK calls)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestrate"))

from swarm.cursor_client import (  # noqa: E402
    CursorCloudClient,
    CursorLocalClient,
    build_client,
    repo_to_url,
)
from swarm.runner import CloudStartupError  # noqa: E402


def test_slug_becomes_github_url():
    assert repo_to_url("mastroke/corticore") == "https://github.com/mastroke/corticore"


def test_https_url_passthrough():
    url = "https://github.com/mastroke/corticore"
    assert repo_to_url(url) == url


def test_ssh_url_passthrough():
    url = "git@github.com:mastroke/corticore.git"
    assert repo_to_url(url) == url


def test_strips_whitespace():
    assert repo_to_url("  mastroke/corticore  ") == "https://github.com/mastroke/corticore"


def test_build_client_cloud():
    client = build_client("cloud", api_key="k")
    assert isinstance(client, CursorCloudClient)
    assert client.runtime == "cloud"


def test_build_client_local(tmp_path):
    client = build_client("local", api_key="k", cwd=tmp_path)
    assert isinstance(client, CursorLocalClient)
    assert client.runtime == "local"
    assert client._cwd == str(tmp_path.resolve())


def test_build_client_local_requires_cwd():
    with pytest.raises(CloudStartupError, match="cwd"):
        build_client("local", api_key="k")


def test_build_client_unknown_runtime():
    with pytest.raises(CloudStartupError, match="unknown runtime"):
        build_client("mars", api_key="k")
