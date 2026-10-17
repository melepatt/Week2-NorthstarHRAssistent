from __future__ import annotations

from pathlib import Path

import pytest

from northstar_rag.indexes import build_indexes, load_indexes
from northstar_rag.retrieval import reciprocal_rank_fusion
from northstar_rag.schemas import ChunkRecord, SearchHit
from tests.fakes import DeterministicEmbeddings


def chunk(chunk_id: str, text: str | None = None) -> ChunkRecord:
    return ChunkRecord(
        chunk_id=chunk_id,
        document_id=f"doc-{chunk_id}",
        document_title=f"Policy {chunk_id}",
        section="1. Scope",
        page=1,
        source_path="policy.pdf",
        text=text or f"Policy text for {chunk_id}",
    )


def hit(chunk_id: str, rank: int, retriever: str) -> SearchHit:
    return SearchHit(
        chunk=chunk(chunk_id),
        rank=rank,
        score=99.0 - rank,
        retriever=retriever,
    )


def test_dense_and_lexical_search_cap_results_at_eight(tmp_path: Path) -> None:
    source = tmp_path / "policy.pdf"
    source.write_bytes(b"policy")
    chunks = [
        ChunkRecord(
            chunk_id=f"chunk-{number:02d}",
            document_id="handbook",
            document_title="Employee Handbook",
            section="1. Scope",
            page=1,
            source_path=str(source),
            text=f"employee workplace policy common token {number}",
        )
        for number in range(12)
    ]
    index_dir = tmp_path / "index"
    embeddings = DeterministicEmbeddings()
    build_indexes(chunks, index_dir, embeddings, embedding_model="fixture")
    indexes = load_indexes(index_dir, embeddings)

    assert len(indexes.dense_search("employee policy", 50)) == 8
    assert len(indexes.lexical_search("employee policy", 50)) == 8


def test_lexical_search_normalizes_case_and_punctuation(tmp_path: Path) -> None:
    source = tmp_path / "policy.pdf"
    source.write_bytes(b"policy")
    index_dir = tmp_path / "index"
    embeddings = DeterministicEmbeddings()
    records = [
        ChunkRecord(
            chunk_id="travel",
            document_id="travel",
            document_title="Travel Policy",
            section="2. Expenses",
            page=2,
            source_path=str(source),
            text="REIMBURSEMENT requires itemized receipts for business travel.",
        ),
        ChunkRecord(
            chunk_id="leave",
            document_id="leave",
            document_title="Leave Policy",
            section="1. Vacation",
            page=1,
            source_path=str(source),
            text="Vacation requests require manager approval.",
        ),
    ]
    build_indexes(records, index_dir, embeddings, embedding_model="fixture")

    results = load_indexes(index_dir, embeddings).lexical_search("Reimbursement?!", 8)

    assert results[0].chunk.chunk_id == "travel"


def test_rrf_deduplicates_and_uses_one_based_component_ranks() -> None:
    fused = reciprocal_rank_fusion(
        [
            [hit("shared", 1, "dense"), hit("dense-only", 2, "dense")],
            [hit("lexical-only", 1, "lexical"), hit("shared", 2, "lexical")],
        ]
    )

    assert [item.chunk.chunk_id for item in fused].count("shared") == 1
    shared = next(item for item in fused if item.chunk.chunk_id == "shared")
    assert shared.score == pytest.approx(1 / 61 + 1 / 62)
    assert shared.component_ranks == (("dense", 1), ("lexical", 2))
    assert shared.retriever == "hybrid"


def test_rrf_ties_sort_by_chunk_id_and_results_are_capped() -> None:
    lists = [[hit(f"chunk-{number:02d}", 1, f"retriever-{number}")] for number in range(12)]

    fused = reciprocal_rank_fusion(lists, limit=10)

    assert [item.chunk.chunk_id for item in fused] == [
        f"chunk-{number:02d}" for number in range(10)
    ]
    assert [item.rank for item in fused] == list(range(1, 11))


def test_rrf_empty_lists_return_empty_output() -> None:
    assert reciprocal_rank_fusion([]) == []
    assert reciprocal_rank_fusion([[], []]) == []
