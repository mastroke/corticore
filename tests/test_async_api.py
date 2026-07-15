import asyncio

import pytest

from corticore import Memory
from corticore.embeddings.local import LocalEmbedder
from corticore.stores.sqlite_store import SQLiteStore


@pytest.fixture
def mem():
    m = Memory(store=SQLiteStore(":memory:"), embedder=LocalEmbedder())
    yield m
    m.close()


def test_aremember_and_arecall(mem):
    async def scenario():
        mid = await mem.aremember("the user's name is Priya")
        assert isinstance(mid, str) and mid
        results = await mem.arecall("what is the user's name?")
        return results

    results = asyncio.run(scenario())
    assert any("Priya" in r.text for r in results)


def test_areflect_returns_report(mem):
    async def scenario():
        await mem.aremember("a lonely fact")
        return await mem.areflect()

    report = asyncio.run(scenario())
    assert report.inspected == 1


def test_async_passes_through_kwargs(mem):
    async def scenario():
        await mem.aremember("alice fact", namespace="alice")
        in_ns = await mem.arecall("alice fact", namespace="alice")
        other_ns = await mem.arecall("alice fact", namespace="bob")
        return in_ns, other_ns

    in_ns, other_ns = asyncio.run(scenario())
    assert in_ns
    assert other_ns == []
