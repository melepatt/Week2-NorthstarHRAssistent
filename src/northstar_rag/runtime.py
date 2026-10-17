from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Lock

from langgraph.graph.state import CompiledStateGraph

from northstar_rag.config import Settings
from northstar_rag.embeddings import NebiusEmbeddings
from northstar_rag.graph import PolicyGraphServices, build_graph
from northstar_rag.indexes import load_indexes
from northstar_rag.nebius import NebiusGateway, validate_configured_models

PROJECT_ROOT = Path(__file__).resolve().parents[2]
INDEX_DIR = PROJECT_ROOT / "data" / "index"


@dataclass(frozen=True, slots=True)
class _RuntimeKey:
    index_dir: str
    nebius_base_url: str
    embedding_model: str
    rerank_model: str
    chat_model: str
    dense_k: int
    lexical_k: int
    fusion_k: int
    rerank_candidates: int
    evidence_k: int
    rerank_min_score: float
    request_timeout_seconds: float
    max_retries: int
    backoff_base_seconds: float


@dataclass(slots=True)
class _RuntimeResource:
    graph: CompiledStateGraph
    gateway: NebiusGateway


_RUNTIME_CACHE: dict[_RuntimeKey, _RuntimeResource] = {}
_CACHE_LOCK = Lock()


def _cache_key(settings: Settings) -> _RuntimeKey:
    return _RuntimeKey(
        index_dir=str(INDEX_DIR.resolve()),
        nebius_base_url=settings.nebius_base_url,
        embedding_model=settings.embedding_model,
        rerank_model=settings.rerank_model,
        chat_model=settings.chat_model,
        dense_k=settings.dense_k,
        lexical_k=settings.lexical_k,
        fusion_k=settings.fusion_k,
        rerank_candidates=settings.rerank_candidates,
        evidence_k=settings.evidence_k,
        rerank_min_score=settings.rerank_min_score,
        request_timeout_seconds=settings.request_timeout_seconds,
        max_retries=settings.max_retries,
        backoff_base_seconds=settings.backoff_base_seconds,
    )


def create_runtime(settings: Settings) -> CompiledStateGraph:
    key = _cache_key(settings)
    with _CACHE_LOCK:
        existing = _RUNTIME_CACHE.get(key)
        if existing is not None:
            return existing.graph

        gateway = NebiusGateway(settings)
        try:
            embeddings = NebiusEmbeddings(
                gateway=gateway,
                model=settings.embedding_model,
            )
            indexes = load_indexes(INDEX_DIR, embeddings)
            validate_configured_models(gateway, settings)
            services = PolicyGraphServices(
                indexes=indexes,
                gateway=gateway,
                settings=settings,
            )
            graph = build_graph(services, settings)
        except Exception:
            gateway.close()
            raise
        _RUNTIME_CACHE[key] = _RuntimeResource(graph=graph, gateway=gateway)
        return graph


def clear_runtime_cache() -> None:
    with _CACHE_LOCK:
        resources = tuple(_RUNTIME_CACHE.values())
        _RUNTIME_CACHE.clear()
    for resource in resources:
        resource.gateway.close()


def runtime_cache_keys() -> tuple[_RuntimeKey, ...]:
    with _CACHE_LOCK:
        return tuple(_RUNTIME_CACHE)
