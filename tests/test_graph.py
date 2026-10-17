from __future__ import annotations

from collections.abc import Callable, Sequence

import pytest

from northstar_rag.config import Settings
from northstar_rag.graph import SERVICE_ERROR, STANDARD_REFUSAL, answer_question, build_graph
from northstar_rag.nebius import NebiusHTTPError, NebiusUnavailableError
from northstar_rag.schemas import ChunkRecord, SearchHit


def make_hit(
    chunk_id: str,
    *,
    rank: int = 1,
    score: float = 0.9,
    retriever: str = "dense",
) -> SearchHit:
    return SearchHit(
        chunk=ChunkRecord(
            chunk_id=chunk_id,
            document_id="leave",
            document_title="Leave and Time Off Policy",
            section="3. Paid Time Off",
            page=2,
            source_path="leave.pdf",
            text=f"Paid leave policy evidence for {chunk_id}.",
        ),
        rank=rank,
        score=score,
        retriever=retriever,
    )


class SteppingClock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        current = self.value
        self.value += 0.001
        return current


class FakeServices:
    def __init__(
        self,
        *,
        rerank_score: float = 0.9,
        answer: str = "Employees receive paid leave [Leave and Time Off Policy, p. 2].",
        dense_hits: Sequence[SearchHit] | None = None,
        lexical_hits: Sequence[SearchHit] | None = None,
        failure: Exception | None = None,
    ) -> None:
        self.clock: Callable[[], float] = SteppingClock()
        self.rerank_score = rerank_score
        self.answer = answer
        self.failure = failure
        self.dense_hits = list(dense_hits) if dense_hits is not None else [make_hit("shared")]
        self.lexical_hits = (
            list(lexical_hits)
            if lexical_hits is not None
            else [make_hit("shared", retriever="lexical")]
        )
        self.dense_k: list[int] = []
        self.lexical_k: list[int] = []
        self.rerank_candidate_counts: list[int] = []
        self.chat_calls = 0

    def dense_search(self, query: str, k: int) -> list[SearchHit]:
        del query
        self.dense_k.append(k)
        if self.failure is not None:
            raise self.failure
        return self.dense_hits

    def lexical_search(self, query: str, k: int) -> list[SearchHit]:
        del query
        self.lexical_k.append(k)
        return self.lexical_hits

    def rerank(self, query: str, hits: Sequence[SearchHit]) -> list[SearchHit]:
        del query
        self.rerank_candidate_counts.append(len(hits))
        return [
            SearchHit(
                chunk=hit.chunk,
                rank=rank,
                score=self.rerank_score,
                retriever="rerank",
                component_ranks=hit.component_ranks,
            )
            for rank, hit in enumerate(hits, start=1)
        ]

    def complete(self, system: str, user: str) -> str:
        del system, user
        self.chat_calls += 1
        if self.failure is not None:
            raise self.failure
        return self.answer


def settings() -> Settings:
    return Settings(nebius_api_key="super-secret-api-key")


def test_blank_question_is_rejected_before_service_calls() -> None:
    services = FakeServices()
    graph = build_graph(services, settings())

    with pytest.raises(ValueError, match="question must not be blank"):
        answer_question(graph, "  \n\t ")

    assert services.dense_k == []
    assert services.lexical_k == []
    assert services.chat_calls == 0


def test_retrieval_fusion_reranking_and_timing_contract() -> None:
    dense = [make_hit(f"dense-{number}", rank=number) for number in range(1, 10)]
    lexical = [
        make_hit(f"lexical-{number}", rank=number, retriever="lexical") for number in range(1, 10)
    ]
    services = FakeServices(dense_hits=dense, lexical_hits=lexical, rerank_score=0.802)

    result = answer_question(build_graph(services, settings()), "  How   much leave?  ")

    assert result.question == "How much leave?"
    assert services.dense_k == [8]
    assert services.lexical_k == [8]
    assert services.rerank_candidate_counts == [10]
    assert len(result.evidence) == 4
    assert services.chat_calls == 1
    assert result.refused is False
    assert [timing.stage for timing in result.timings] == [
        "retrieve_dense",
        "retrieve_lexical",
        "fuse_results",
        "rerank_results",
        "assess_evidence",
        "generate_answer",
        "validate_citations",
    ]
    assert all(timing.elapsed_ms == pytest.approx(1.0) for timing in result.timings)


def test_score_below_threshold_refuses_without_chat_completion() -> None:
    services = FakeServices(rerank_score=0.801)

    result = answer_question(build_graph(services, settings()), "How much leave?")

    assert result.refused is True
    assert result.answer == STANDARD_REFUSAL
    assert services.chat_calls == 0
    assert [timing.stage for timing in result.timings][-1] == "build_refusal"


def test_empty_evidence_refuses_without_rerank_or_chat() -> None:
    services = FakeServices(dense_hits=[], lexical_hits=[])

    result = answer_question(build_graph(services, settings()), "Is lunch provided?")

    assert result.refused is True
    assert result.answer == STANDARD_REFUSAL
    assert services.rerank_candidate_counts == []
    assert services.chat_calls == 0


@pytest.mark.parametrize(
    "generated_answer",
    [
        "Employees receive paid leave [Imaginary Policy, p. 99].",
        "Employees receive paid leave.",
    ],
)
def test_invalid_generated_citations_are_replaced_with_standard_refusal(
    generated_answer: str,
) -> None:
    services = FakeServices(answer=generated_answer)

    result = answer_question(build_graph(services, settings()), "How much leave?")

    assert result.refused is True
    assert result.answer == STANDARD_REFUSAL
    assert result.citations == ()
    assert result.refusal_reason == "citation_validation_failed"


@pytest.mark.parametrize(
    ("failure", "expected_code"),
    [
        (NebiusUnavailableError("super-secret-api-key timeout"), "service_unavailable"),
        (NebiusHTTPError("super-secret-api-key status 401"), "provider_request_failed"),
    ],
)
def test_provider_errors_return_safe_result_without_secret(
    failure: Exception,
    expected_code: str,
) -> None:
    services = FakeServices(failure=failure)

    result = answer_question(build_graph(services, settings()), "How much leave?")

    assert result.refused is True
    assert result.answer == SERVICE_ERROR
    assert result.error_code == expected_code
    assert "super-secret-api-key" not in str(result)


def test_refusal_path_never_calls_chat_even_if_chat_would_fail() -> None:
    services = FakeServices(rerank_score=0.1, failure=None)

    result = answer_question(build_graph(services, settings()), "Unknown question")

    assert result.refused is True
    assert services.chat_calls == 0
