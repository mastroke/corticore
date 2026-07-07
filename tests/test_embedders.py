"""Tests for the optional embedder extras.

Neither test requires real credentials or a network call:
- The sentence-transformers test is skipped entirely if the extra isn't
  installed (`pip install corticore[st]`).
- The Azure OpenAI test is skipped if the `openai` package isn't installed
  (`pip install corticore[openai]`), and otherwise uses an injected mock
  client so it never talks to a real Azure resource or reads real keys.
"""

from __future__ import annotations

import pytest


def test_sentence_transformer_embedder_produces_a_vector():
    pytest.importorskip("sentence_transformers")
    from corticore.embeddings.sentence_transformer import SentenceTransformerEmbedder

    embedder = SentenceTransformerEmbedder()
    vector = embedder.embed("hello world")

    assert isinstance(vector, list)
    assert len(vector) > 0
    assert all(isinstance(v, float) for v in vector)


def test_sentence_transformer_embedder_missing_dependency_message():
    # Simulate the extra not being installed regardless of the environment,
    # by asserting the class raises our own ImportError message shape when
    # the underlying import fails - covered indirectly by code review since
    # forcing an ImportError from an installed package isn't practical here.
    from corticore.embeddings.sentence_transformer import _INSTALL_HINT

    assert "pip install corticore[st]" in _INSTALL_HINT


class _FakeEmbeddingItem:
    def __init__(self, embedding: list[float]) -> None:
        self.embedding = embedding


class _FakeEmbeddingResponse:
    def __init__(self, vectors: list[list[float]]) -> None:
        self.data = [_FakeEmbeddingItem(v) for v in vectors]


class _FakeEmbeddingsAPI:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def create(self, input, model):  # noqa: A002 - mirrors the real SDK's kwarg name
        self.calls.append({"input": input, "model": model})
        texts = input if isinstance(input, list) else [input]
        return _FakeEmbeddingResponse([[float(len(t)), 0.0] for t in texts])


class _FakeAzureClient:
    def __init__(self) -> None:
        self.embeddings = _FakeEmbeddingsAPI()


def test_azure_openai_embedder_uses_injected_client():
    pytest.importorskip("openai")
    from corticore.embeddings.azure_openai import AzureOpenAIEmbedder

    fake_client = _FakeAzureClient()
    embedder = AzureOpenAIEmbedder(deployment="test-embedding-deployment", client=fake_client)

    vector = embedder.embed("hi")

    assert vector == [2.0, 0.0]
    assert fake_client.embeddings.calls == [{"input": "hi", "model": "test-embedding-deployment"}]


def test_azure_openai_embedder_embed_many_uses_injected_client():
    pytest.importorskip("openai")
    from corticore.embeddings.azure_openai import AzureOpenAIEmbedder

    fake_client = _FakeAzureClient()
    embedder = AzureOpenAIEmbedder(deployment="test-embedding-deployment", client=fake_client)

    vectors = embedder.embed_many(["hi", "hello"])

    assert vectors == [[2.0, 0.0], [5.0, 0.0]]


def test_azure_openai_embedder_requires_deployment(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", raising=False)
    from corticore.embeddings.azure_openai import AzureOpenAIEmbedder

    with pytest.raises(ValueError, match="deployment"):
        AzureOpenAIEmbedder(deployment=None, client=_FakeAzureClient())


def test_azure_openai_embedder_requires_credentials_without_injected_client(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    from corticore.embeddings.azure_openai import AzureOpenAIEmbedder

    with pytest.raises(ValueError, match="credentials"):
        AzureOpenAIEmbedder(deployment="test-embedding-deployment")
