from __future__ import annotations

import httpx
import pytest

from northstar_rag.config import Settings
from northstar_rag.nebius import NebiusGateway, NebiusResponseError
from northstar_rag.reranking import rerank_hits
from northstar_rag.schemas import ChunkRecord, SearchHit


class FakeRerankGateway:
    def __init__(self, scores: list[float]) -> None:
        self.scores = scores

    def rerank(self, query: str, documents: list[str], model: str) -> list[float]:
        assert query == "leave"
        assert documents == ["text zero", "text one", "text two"]
        assert model == "rerank-model"
        return self.scores


def hit(index: int) -> SearchHit:
    chunk = ChunkRecord(
        chunk_id=f"chunk-{index}",
        document_id="leave-and-time-off",
        document_title="Leave and Time Off Policy",
        section="Paid Time Off",
        page=index + 1,
        source_path="data/policies/leave-and-time-off.pdf",
        text=f"text {['zero', 'one', 'two'][index]}",
    )
    return SearchHit(chunk=chunk, rank=index + 1, score=0.1, retriever="fused")


def test_rerank_hits_maps_scores_and_uses_original_order_for_ties() -> None:
    reranked = rerank_hits(
        "leave",
        [hit(0), hit(1), hit(2)],
        FakeRerankGateway([0.2, 0.9, 0.9]),
        "rerank-model",
    )

    assert [item.chunk.chunk_id for item in reranked] == ["chunk-1", "chunk-2", "chunk-0"]
    assert [item.rank for item in reranked] == [1, 2, 3]
    assert [item.score for item in reranked] == [0.9, 0.9, 0.2]
    assert all(item.retriever == "rerank" for item in reranked)


def test_gateway_rejects_inconsistent_rerank_embedding_dimensions() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 0, "embedding": [1.0, 0.0]},
                    {"index": 1, "embedding": [1.0]},
                    {"index": 2, "embedding": [0.0, 1.0]},
                ]
            },
        )

    gateway = NebiusGateway(
        Settings.from_env({"NEBIUS_API_KEY": "test-key"}),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleeper=lambda _: None,
    )

    with pytest.raises(NebiusResponseError, match="dimensions"):
        gateway.rerank("question", ["zero", "one"], "rerank-model")


def test_gateway_rejects_zero_magnitude_rerank_embeddings() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 0, "embedding": [0.0, 0.0]},
                    {"index": 1, "embedding": [1.0, 0.0]},
                ]
            },
        )

    gateway = NebiusGateway(
        Settings.from_env({"NEBIUS_API_KEY": "test-key"}),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleeper=lambda _: None,
    )

    with pytest.raises(NebiusResponseError, match="zero magnitude"):
        gateway.rerank("question", ["zero"], "rerank-model")
