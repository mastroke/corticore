"""Optional semantic embedder backed by an Azure OpenAI embeddings deployment.

Uses the `openai` package's `AzureOpenAI` client (the same client class
covers both direct OpenAI and Azure OpenAI - only the constructor arguments
differ). Not imported anywhere by default, so the base `corticore` package
stays dependency-free.

Credentials are **never** hardcoded or requested by corticore itself. Supply
them via environment variables (recommended - copy `.env.example` to `.env`
and fill in your own values, then load it however you prefer, e.g. with
`python-dotenv` or your shell) or by passing them explicitly to the
constructor:

    AZURE_OPENAI_API_KEY        - your Azure OpenAI resource key
    AZURE_OPENAI_ENDPOINT       - e.g. https://<resource>.openai.azure.com
    AZURE_OPENAI_API_VERSION    - e.g. 2024-10-21 (check your resource's
                                   supported API versions in the Azure portal)
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT - the *deployment name* you gave your
                                   embedding model in Azure AI Studio, not
                                   the underlying model name

Install with: pip install corticore[openai]
"""

from __future__ import annotations

import os
from typing import Any, Optional

from corticore.embeddings.base import Embedder

_INSTALL_HINT = (
    "AzureOpenAIEmbedder requires the 'openai' package. "
    "Install it with: pip install corticore[openai]"
)


class AzureOpenAIEmbedder(Embedder):
    """Wraps an Azure OpenAI embeddings deployment behind the `Embedder` interface."""

    def __init__(
        self,
        deployment: Optional[str] = None,
        api_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        api_version: Optional[str] = None,
        client: Optional[Any] = None,
    ) -> None:
        self.deployment = deployment or os.environ.get("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")
        if not self.deployment:
            raise ValueError(
                "AzureOpenAIEmbedder needs a deployment name: pass deployment=... "
                "or set AZURE_OPENAI_EMBEDDING_DEPLOYMENT."
            )

        if client is not None:
            # Allows tests (and advanced callers) to inject a pre-built or
            # mocked client without touching environment variables at all.
            self._client = client
            return

        api_key = api_key or os.environ.get("AZURE_OPENAI_API_KEY")
        endpoint = endpoint or os.environ.get("AZURE_OPENAI_ENDPOINT")
        api_version = api_version or os.environ.get("AZURE_OPENAI_API_VERSION")
        if not api_key or not endpoint:
            raise ValueError(
                "AzureOpenAIEmbedder needs credentials: set AZURE_OPENAI_API_KEY "
                "and AZURE_OPENAI_ENDPOINT (or pass api_key=/endpoint= explicitly). "
                "See .env.example."
            )

        try:
            from openai import AzureOpenAI
        except ImportError as exc:  # pragma: no cover - exercised via importorskip
            raise ImportError(_INSTALL_HINT) from exc

        self._client = AzureOpenAI(
            api_key=api_key,
            azure_endpoint=endpoint,
            api_version=api_version or "2024-10-21",
        )

    def embed(self, text: str) -> list[float]:
        response = self._client.embeddings.create(input=text, model=self.deployment)
        return list(response.data[0].embedding)

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        response = self._client.embeddings.create(input=texts, model=self.deployment)
        return [list(item.embedding) for item in response.data]
