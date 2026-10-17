from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from langchain_core.embeddings import Embeddings


class EmbeddingResponseError(ValueError):
    """Raised when embedding vectors cannot safely enter the dense index."""


class EmbeddingGateway(Protocol):
    def embed(self, texts: Sequence[str], model: str) -> list[list[float]]: ...


@dataclass(slots=True)
class NebiusEmbeddings(Embeddings):
    gateway: EmbeddingGateway
    model: str

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors = self.gateway.embed(texts, self.model)
        if len(vectors) != len(texts):
            raise EmbeddingResponseError("embedding response item count does not match input")
        if not vectors:
            return []
        dimensions = {len(vector) for vector in vectors}
        if len(dimensions) != 1 or 0 in dimensions:
            raise EmbeddingResponseError("embedding vectors have inconsistent dimensions")
        return vectors

    def embed_query(self, text: str) -> list[float]:
        vectors = self.embed_documents([text])
        if not vectors:
            raise EmbeddingResponseError("embedding query returned no vector")
        return vectors[0]
