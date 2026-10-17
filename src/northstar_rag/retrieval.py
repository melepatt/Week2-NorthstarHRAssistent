from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from northstar_rag.schemas import ChunkRecord, SearchHit


@dataclass(slots=True)
class _FusedCandidate:
    chunk: ChunkRecord
    score: float = 0.0
    component_ranks: list[tuple[str, int]] = field(default_factory=list)
    seen_retrievers: set[str] = field(default_factory=set)


def reciprocal_rank_fusion(
    result_lists: Sequence[Sequence[SearchHit]],
    k: int = 60,
    limit: int = 10,
) -> list[SearchHit]:
    if k < 1:
        raise ValueError("k must be positive")
    if limit < 1:
        return []

    candidates: dict[str, _FusedCandidate] = {}
    for results in result_lists:
        for hit in results:
            candidate = candidates.setdefault(
                hit.chunk.chunk_id,
                _FusedCandidate(chunk=hit.chunk),
            )
            if hit.retriever in candidate.seen_retrievers:
                continue
            candidate.seen_retrievers.add(hit.retriever)
            candidate.score += 1.0 / (k + hit.rank)
            candidate.component_ranks.append((hit.retriever, hit.rank))

    ordered = sorted(
        candidates.values(),
        key=lambda candidate: (-candidate.score, candidate.chunk.chunk_id),
    )[:limit]
    return [
        SearchHit(
            chunk=candidate.chunk,
            rank=rank,
            score=candidate.score,
            retriever="hybrid",
            component_ranks=tuple(candidate.component_ranks),
        )
        for rank, candidate in enumerate(ordered, start=1)
    ]
