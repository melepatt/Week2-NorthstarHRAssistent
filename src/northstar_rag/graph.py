from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import partial
from typing import Protocol, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from northstar_rag.citations import validate_grounded_answer
from northstar_rag.config import Settings
from northstar_rag.indexes import HybridIndexes
from northstar_rag.nebius import (
    NebiusError,
    NebiusGateway,
    NebiusHTTPError,
    NebiusResponseError,
    NebiusUnavailableError,
)
from northstar_rag.prompts import build_answer_messages
from northstar_rag.reranking import rerank_hits
from northstar_rag.retrieval import reciprocal_rank_fusion
from northstar_rag.schemas import AnswerResult, Citation, SearchHit, StageTiming

STANDARD_REFUSAL = (
    "The available Northstar Labs policies do not provide enough information to answer that "
    "question. Please contact People Operations for assistance."
)
SERVICE_ERROR = (
    "The policy service is temporarily unavailable. Please try again later or contact People "
    "Operations for assistance."
)


class QueryState(TypedDict, total=False):
    question: str
    dense_hits: list[SearchHit]
    lexical_hits: list[SearchHit]
    fused_hits: list[SearchHit]
    reranked_hits: list[SearchHit]
    evidence_confidence: float
    answer_text: str
    citations: tuple[Citation, ...]
    refused: bool
    refusal_reason: str | None
    error_code: str | None
    timings: tuple[StageTiming, ...]


class GraphServices(Protocol):
    clock: Callable[[], float]

    def dense_search(self, query: str, k: int) -> list[SearchHit]: ...

    def lexical_search(self, query: str, k: int) -> list[SearchHit]: ...

    def rerank(self, query: str, hits: Sequence[SearchHit]) -> list[SearchHit]: ...

    def complete(self, system: str, user: str) -> str: ...


@dataclass(slots=True)
class PolicyGraphServices:
    indexes: HybridIndexes
    gateway: NebiusGateway
    settings: Settings
    clock: Callable[[], float] = time.perf_counter

    def dense_search(self, query: str, k: int) -> list[SearchHit]:
        return self.indexes.dense_search(query, k)

    def lexical_search(self, query: str, k: int) -> list[SearchHit]:
        return self.indexes.lexical_search(query, k)

    def rerank(self, query: str, hits: Sequence[SearchHit]) -> list[SearchHit]:
        return rerank_hits(query, hits, self.gateway, self.settings.rerank_model)

    def complete(self, system: str, user: str) -> str:
        return self.gateway.complete(system, user, self.settings.chat_model)


def _timing(
    state: QueryState,
    stage: str,
    started_at: float,
    services: GraphServices,
) -> tuple[StageTiming, ...]:
    elapsed_ms = max((services.clock() - started_at) * 1000.0, 0.0)
    return (*state.get("timings", ()), StageTiming(stage=stage, elapsed_ms=elapsed_ms))


def retrieve_dense(
    state: QueryState,
    *,
    services: GraphServices,
    settings: Settings,
) -> QueryState:
    started_at = services.clock()
    hits = services.dense_search(state["question"], settings.dense_k)[: settings.dense_k]
    return {
        "dense_hits": hits,
        "timings": _timing(state, "retrieve_dense", started_at, services),
    }


def retrieve_lexical(
    state: QueryState,
    *,
    services: GraphServices,
    settings: Settings,
) -> QueryState:
    started_at = services.clock()
    hits = services.lexical_search(state["question"], settings.lexical_k)[: settings.lexical_k]
    return {
        "lexical_hits": hits,
        "timings": _timing(state, "retrieve_lexical", started_at, services),
    }


def fuse_results(
    state: QueryState,
    *,
    services: GraphServices,
    settings: Settings,
) -> QueryState:
    started_at = services.clock()
    fused = reciprocal_rank_fusion(
        [state.get("dense_hits", []), state.get("lexical_hits", [])],
        k=settings.fusion_k,
        limit=settings.rerank_candidates,
    )
    return {
        "fused_hits": fused,
        "timings": _timing(state, "fuse_results", started_at, services),
    }


def _ranked_evidence(hits: Sequence[SearchHit], limit: int) -> list[SearchHit]:
    ordered = sorted(hits, key=lambda hit: (-hit.score, hit.chunk.chunk_id))[:limit]
    return [
        SearchHit(
            chunk=hit.chunk,
            rank=rank,
            score=hit.score,
            retriever=hit.retriever,
            component_ranks=hit.component_ranks,
        )
        for rank, hit in enumerate(ordered, start=1)
    ]


def rerank_results(
    state: QueryState,
    *,
    services: GraphServices,
    settings: Settings,
) -> QueryState:
    started_at = services.clock()
    fused = state.get("fused_hits", [])[: settings.rerank_candidates]
    reranked = services.rerank(state["question"], fused) if fused else []
    evidence = _ranked_evidence(reranked, settings.evidence_k)
    return {
        "reranked_hits": evidence,
        "timings": _timing(state, "rerank_results", started_at, services),
    }


def assess_evidence(
    state: QueryState,
    *,
    services: GraphServices,
    settings: Settings,
) -> QueryState:
    del settings
    started_at = services.clock()
    evidence = state.get("reranked_hits", [])
    confidence = max((hit.score for hit in evidence), default=0.0)
    return {
        "evidence_confidence": confidence,
        "timings": _timing(state, "assess_evidence", started_at, services),
    }


def generate_answer(
    state: QueryState,
    *,
    services: GraphServices,
    settings: Settings,
) -> QueryState:
    del settings
    started_at = services.clock()
    system, user = build_answer_messages(state["question"], state.get("reranked_hits", []))
    answer = services.complete(system, user)
    return {
        "answer_text": answer,
        "refused": False,
        "timings": _timing(state, "generate_answer", started_at, services),
    }


def build_refusal(
    state: QueryState,
    *,
    services: GraphServices,
    settings: Settings,
) -> QueryState:
    del settings
    started_at = services.clock()
    return {
        "answer_text": STANDARD_REFUSAL,
        "citations": (),
        "refused": True,
        "refusal_reason": "insufficient_evidence",
        "timings": _timing(state, "build_refusal", started_at, services),
    }


def validate_citations(
    state: QueryState,
    *,
    services: GraphServices,
    settings: Settings,
) -> QueryState:
    del settings
    started_at = services.clock()
    validation = validate_grounded_answer(
        state.get("answer_text", ""),
        state.get("reranked_hits", []),
    )
    if validation.valid:
        result: QueryState = {
            "citations": validation.citations,
            "refused": False,
            "refusal_reason": None,
        }
    else:
        result = {
            "answer_text": STANDARD_REFUSAL,
            "citations": (),
            "refused": True,
            "refusal_reason": "citation_validation_failed",
        }
    result["timings"] = _timing(state, "validate_citations", started_at, services)
    return result


def _route_after_assessment(state: QueryState, settings: Settings) -> str:
    if (
        state.get("reranked_hits")
        and state.get("evidence_confidence", 0.0) >= settings.rerank_min_score
    ):
        return "generate_answer"
    return "build_refusal"


def build_graph(
    services: GraphServices,
    settings: Settings,
) -> CompiledStateGraph:
    workflow = StateGraph(QueryState)
    nodes = {
        "retrieve_dense": retrieve_dense,
        "retrieve_lexical": retrieve_lexical,
        "fuse_results": fuse_results,
        "rerank_results": rerank_results,
        "assess_evidence": assess_evidence,
        "generate_answer": generate_answer,
        "build_refusal": build_refusal,
        "validate_citations": validate_citations,
    }
    for name, node in nodes.items():
        workflow.add_node(name, partial(node, services=services, settings=settings))

    workflow.add_edge(START, "retrieve_dense")
    workflow.add_edge("retrieve_dense", "retrieve_lexical")
    workflow.add_edge("retrieve_lexical", "fuse_results")
    workflow.add_edge("fuse_results", "rerank_results")
    workflow.add_edge("rerank_results", "assess_evidence")
    workflow.add_conditional_edges(
        "assess_evidence",
        partial(_route_after_assessment, settings=settings),
        {
            "generate_answer": "generate_answer",
            "build_refusal": "build_refusal",
        },
    )
    workflow.add_edge("generate_answer", "validate_citations")
    workflow.add_edge("validate_citations", END)
    workflow.add_edge("build_refusal", END)
    return workflow.compile()


def _safe_service_result(question: str, error: NebiusError) -> AnswerResult:
    if isinstance(error, NebiusUnavailableError):
        error_code = "service_unavailable"
    elif isinstance(error, NebiusHTTPError):
        error_code = "provider_request_failed"
    elif isinstance(error, NebiusResponseError):
        error_code = "provider_response_invalid"
    else:
        error_code = "provider_error"
    return AnswerResult(
        question=question,
        answer=SERVICE_ERROR,
        refused=True,
        refusal_reason="service_error",
        error_code=error_code,
    )


def answer_question(graph: CompiledStateGraph, question: str) -> AnswerResult:
    normalized_question = " ".join(question.split())
    if not normalized_question:
        raise ValueError("question must not be blank")
    try:
        state: QueryState = graph.invoke(
            {
                "question": normalized_question,
                "timings": (),
            }
        )
    except NebiusError as error:
        return _safe_service_result(normalized_question, error)

    return AnswerResult(
        question=normalized_question,
        answer=state["answer_text"],
        refused=state.get("refused", False),
        citations=state.get("citations", ()),
        evidence=tuple(state.get("reranked_hits", [])),
        refusal_reason=state.get("refusal_reason"),
        error_code=state.get("error_code"),
        timings=state.get("timings", ()),
    )
