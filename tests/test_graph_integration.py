from __future__ import annotations

import re
import time
from collections.abc import Sequence
from pathlib import Path

from northstar_rag.config import Settings
from northstar_rag.graph import STANDARD_REFUSAL, answer_question, build_graph
from northstar_rag.indexes import HybridIndexes, build_indexes, load_indexes
from northstar_rag.schemas import ChunkRecord, SearchHit
from tests.fakes import DeterministicEmbeddings


class OfflineGraphServices:
    clock = time.perf_counter

    def __init__(self, indexes: HybridIndexes) -> None:
        self.indexes = indexes
        self.chat_calls = 0

    def dense_search(self, query: str, k: int) -> list[SearchHit]:
        return self.indexes.dense_search(query, k)

    def lexical_search(self, query: str, k: int) -> list[SearchHit]:
        return self.indexes.lexical_search(query, k)

    def rerank(self, query: str, hits: Sequence[SearchHit]) -> list[SearchHit]:
        query_tokens = set(re.findall(r"\w+", query.casefold()))
        reranked: list[SearchHit] = []
        for hit in hits:
            evidence_tokens = set(re.findall(r"\w+", hit.chunk.text.casefold()))
            score = 0.9 if query_tokens & evidence_tokens else 0.1
            reranked.append(
                SearchHit(
                    chunk=hit.chunk,
                    rank=1,
                    score=score,
                    retriever="rerank",
                    component_ranks=hit.component_ranks,
                )
            )
        reranked.sort(key=lambda hit: (-hit.score, hit.chunk.chunk_id))
        return [
            SearchHit(
                chunk=hit.chunk,
                rank=rank,
                score=hit.score,
                retriever=hit.retriever,
                component_ranks=hit.component_ranks,
            )
            for rank, hit in enumerate(reranked, start=1)
        ]

    def complete(self, system: str, user: str) -> str:
        del system
        self.chat_calls += 1
        title = re.search(r"Document title: (.+)", user)
        page = re.search(r"Page: (\d+)", user)
        assert title is not None and page is not None
        return f"Manager approval is required [{title.group(1)}, p. {page.group(1)}]."


def build_fixture_indexes(tmp_path: Path) -> HybridIndexes:
    source = tmp_path / "policies.pdf"
    source.write_bytes(b"offline controlled policies")
    chunks = [
        ChunkRecord(
            chunk_id="leave-approval",
            document_id="leave",
            document_title="Leave and Time Off Policy",
            section="3. Paid Time Off",
            page=2,
            source_path=str(source),
            text="Vacation leave requests require manager approval before travel.",
        ),
        ChunkRecord(
            chunk_id="security-device",
            document_id="security",
            document_title="Remote Work and Information Security Policy",
            section="4. Devices",
            page=3,
            source_path=str(source),
            text="Company devices require encryption and security updates.",
        ),
    ]
    embeddings = DeterministicEmbeddings()
    index_dir = tmp_path / "index"
    build_indexes(chunks, index_dir, embeddings, embedding_model="fixture")
    return load_indexes(index_dir, embeddings)


def test_complete_offline_graph_supports_grounded_answer_and_refusal(tmp_path: Path) -> None:
    services = OfflineGraphServices(build_fixture_indexes(tmp_path))
    graph = build_graph(services, Settings(nebius_api_key="offline"))

    supported = answer_question(graph, "Does vacation leave require manager approval?")
    unrelated = answer_question(graph, "Is catered lunch provided every Friday?")

    assert supported.refused is False
    assert "[Leave and Time Off Policy, p. 2]" in supported.answer
    assert supported.citations[0].document_title == "Leave and Time Off Policy"
    assert supported.citations[0].page == 2
    assert unrelated.refused is True
    assert unrelated.answer == STANDARD_REFUSAL
    assert services.chat_calls == 1
