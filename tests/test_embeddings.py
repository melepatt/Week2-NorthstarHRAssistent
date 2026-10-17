from __future__ import annotations

import pytest

from northstar_rag.embeddings import EmbeddingResponseError, NebiusEmbeddings


class FakeEmbeddingGateway:
    def __init__(self, vectors: list[list[float]]) -> None:
        self.vectors = vectors
        self.calls: list[tuple[list[str], str]] = []

    def embed(self, texts: list[str], model: str) -> list[list[float]]:
        self.calls.append((list(texts), model))
        return self.vectors


def test_embeddings_preserve_gateway_input_and_output_order() -> None:
    gateway = FakeEmbeddingGateway([[2.0, 2.5], [1.0, 1.5]])
    embeddings = NebiusEmbeddings(gateway=gateway, model="embedding-model")

    result = embeddings.embed_documents(["second", "first"])

    assert result == [[2.0, 2.5], [1.0, 1.5]]
    assert gateway.calls == [(["second", "first"], "embedding-model")]


def test_embeddings_reject_inconsistent_vector_dimensions() -> None:
    embeddings = NebiusEmbeddings(
        gateway=FakeEmbeddingGateway([[1.0, 2.0], [3.0]]),
        model="embedding-model",
    )

    with pytest.raises(EmbeddingResponseError, match="dimensions"):
        embeddings.embed_documents(["first", "second"])


def test_embed_query_returns_the_single_vector() -> None:
    gateway = FakeEmbeddingGateway([[1.0, 2.0]])
    embeddings = NebiusEmbeddings(gateway=gateway, model="embedding-model")

    assert embeddings.embed_query("question") == [1.0, 2.0]
    assert gateway.calls == [(["question"], "embedding-model")]
