import pytest

from corticore import Memory
from corticore.embeddings.local import LocalEmbedder
from corticore.stores.sqlite_store import SQLiteStore


@pytest.fixture
def mem():
    m = Memory(store=SQLiteStore(":memory:"), embedder=LocalEmbedder())
    yield m
    m.close()


def test_recall_is_scoped_to_its_namespace(mem):
    mem.remember("alice likes dark mode", namespace="alice")
    mem.remember("bob likes light mode", namespace="bob")

    alice_results = mem.recall("likes mode", namespace="alice")
    assert alice_results
    assert all("alice" in r.text for r in alice_results)


def test_recall_never_leaks_across_namespaces(mem):
    mem.remember("bob likes light mode", namespace="bob")

    # Query from alice's namespace should not see bob's memory at all.
    assert mem.recall("likes mode", namespace="alice") == []


def test_recall_none_namespace_searches_everything(mem):
    mem.remember("alice fact about testing", namespace="alice")
    mem.remember("bob fact about testing", namespace="bob")

    results = mem.recall("fact about testing", namespace=None)
    namespaces = {r.text.split()[0] for r in results}
    assert {"alice", "bob"} <= namespaces


def test_default_namespace_preserves_single_tenant_behavior(mem):
    mem.remember("the user's name is Priya")
    results = mem.recall("what is the user's name?")
    assert any("Priya" in r.text for r in results)


def test_reflect_does_not_merge_across_namespaces(mem):
    # Identical text in two namespaces must both survive consolidation.
    mem.remember("the deployment key is rotated weekly", namespace="team-a")
    mem.remember("the deployment key is rotated weekly", namespace="team-b")

    report = mem.reflect()

    assert report.merged == []
    assert report.superseded == []
    assert mem.recall("deployment key", namespace="team-a")
    assert mem.recall("deployment key", namespace="team-b")
