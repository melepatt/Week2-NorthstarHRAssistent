from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from northstar_rag.schemas import SearchHit


class RerankGateway(Protocol):
    def rerank(self, query: str, documents: Sequence[str], model: str) -> list[float]: ...


def rerank_hits(
    query: str,
    hits: Sequence[SearchHit],
    gateway: RerankGateway,
    model: str,
) -> list[SearchHit]:
    if not hits:
        return []
    scores = gateway.rerank(query, [hit.chunk.text for hit in hits], model)
    if len(scores) != len(hits):
        raise ValueError("rerank score count does not match candidate count")

    scored = list(enumerate(zip(hits, scores, strict=True)))
    scored.sort(key=lambda item: (-item[1][1], item[0]))
    reranked: list[SearchHit] = []
    for rank, (_, (hit, score)) in enumerate(scored, start=1):
        component_ranks = hit.component_ranks or ((hit.retriever, hit.rank),)
        reranked.append(
            SearchHit(
                chunk=hit.chunk,
                rank=rank,
                score=score,
                retriever="rerank",
                component_ranks=component_ranks,
            )
        )
    return reranked
