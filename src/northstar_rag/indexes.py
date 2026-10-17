from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings
from langchain_core.embeddings import Embeddings
from rank_bm25 import BM25Plus

from northstar_rag.schemas import ChunkRecord, SearchHit

INDEX_SCHEMA_VERSION = 1
COLLECTION_NAME = "northstar_policy_chunks"
MAX_RETRIEVAL_RESULTS = 8
INDEX_INSTRUCTION = "Run `python scripts/ingest.py` to build the policy index."
TOKEN_PATTERN = re.compile(r"\w+", re.UNICODE)


class IndexNotReadyError(RuntimeError):
    """Raised when a complete, internally consistent index cannot be loaded."""


@dataclass(frozen=True, slots=True)
class IndexManifest:
    schema_version: int
    embedding_model: str
    source_hashes: dict[str, str]
    chunk_count: int


def tokenize_for_bm25(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return TOKEN_PATTERN.findall(normalized)


def _not_ready(reason: str) -> IndexNotReadyError:
    return IndexNotReadyError(f"Policy index is not ready: {reason}. {INDEX_INSTRUCTION}")


def _source_hashes(chunks: Sequence[ChunkRecord]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for source_name in sorted({chunk.source_path for chunk in chunks}):
        source = Path(source_name)
        if not source.is_file():
            raise _not_ready(f"source file is missing: {source}")
        hashes[source_name] = hashlib.sha256(source.read_bytes()).hexdigest()
    return hashes


def _write_json(path: Path, value: Any) -> None:
    serialized = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    path.write_text(serialized, encoding="utf-8")


def _chroma_client(path: Path) -> chromadb.ClientAPI:
    return chromadb.PersistentClient(
        path=str(path),
        settings=ChromaSettings(anonymized_telemetry=False),
    )


def build_indexes(
    chunks: Sequence[ChunkRecord],
    index_dir: Path,
    embeddings: Embeddings,
    *,
    embedding_model: str | None = None,
) -> IndexManifest:
    if not chunks:
        raise _not_ready("no chunks were produced")
    resolved_embedding_model = embedding_model or getattr(
        embeddings,
        "model",
        type(embeddings).__name__,
    )
    if not isinstance(resolved_embedding_model, str) or not resolved_embedding_model.strip():
        raise ValueError("embedding_model must not be blank")

    canonical = sorted(chunks, key=lambda chunk: chunk.chunk_id)
    chunk_ids = [chunk.chunk_id for chunk in canonical]
    if len(set(chunk_ids)) != len(chunk_ids):
        raise _not_ready("chunk IDs are not unique")

    index_dir.mkdir(parents=True, exist_ok=True)
    chroma_dir = index_dir / "chroma"
    chroma_dir.mkdir()
    vectors = embeddings.embed_documents([chunk.text for chunk in canonical])
    if len(vectors) != len(canonical):
        raise _not_ready("embedding response count does not match chunk count")

    try:
        client = _chroma_client(chroma_dir)
        collection = client.create_collection(
            COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        collection.add(
            ids=chunk_ids,
            embeddings=vectors,
            documents=[chunk.text for chunk in canonical],
            metadatas=[
                {
                    "document_id": chunk.document_id,
                    "document_title": chunk.document_title,
                    "section": chunk.section,
                    "page": chunk.page,
                    "source_path": chunk.source_path,
                }
                for chunk in canonical
            ],
        )
    except Exception as error:
        raise _not_ready("dense index could not be created") from error

    manifest = IndexManifest(
        schema_version=INDEX_SCHEMA_VERSION,
        embedding_model=resolved_embedding_model.strip(),
        source_hashes=_source_hashes(canonical),
        chunk_count=len(canonical),
    )
    _write_json(index_dir / "chunks.json", [chunk.to_dict() for chunk in canonical])
    _write_json(index_dir / "manifest.json", asdict(manifest))
    return manifest


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise _not_ready(f"{path.name} is missing or corrupt") from error


def _load_manifest(path: Path) -> IndexManifest:
    raw = _load_json(path)
    try:
        manifest = IndexManifest(**raw)
    except (TypeError, ValueError) as error:
        raise _not_ready("manifest.json has an invalid shape") from error
    if (
        manifest.schema_version != INDEX_SCHEMA_VERSION
        or not isinstance(manifest.embedding_model, str)
        or not manifest.embedding_model.strip()
        or not isinstance(manifest.source_hashes, dict)
        or not all(
            isinstance(name, str) and isinstance(digest, str)
            for name, digest in manifest.source_hashes.items()
        )
        or not isinstance(manifest.chunk_count, int)
        or manifest.chunk_count < 1
    ):
        raise _not_ready("manifest.json contains invalid values")
    return manifest


def _load_chunks(path: Path) -> list[ChunkRecord]:
    raw = _load_json(path)
    if not isinstance(raw, list) or not raw:
        raise _not_ready("chunks.json must contain at least one chunk")
    try:
        chunks = [ChunkRecord.from_dict(item) for item in raw]
    except (TypeError, ValueError) as error:
        raise _not_ready("chunks.json contains an invalid chunk") from error
    chunk_ids = [chunk.chunk_id for chunk in chunks]
    if chunk_ids != sorted(chunk_ids) or len(chunk_ids) != len(set(chunk_ids)):
        raise _not_ready("chunks.json is not canonical")
    return chunks


class HybridIndexes:
    def __init__(
        self,
        *,
        collection: Any,
        chunks: Sequence[ChunkRecord],
        embeddings: Embeddings,
        manifest: IndexManifest,
    ) -> None:
        self.manifest = manifest
        self._collection = collection
        self._chunks = tuple(chunks)
        self._chunks_by_id = {chunk.chunk_id: chunk for chunk in chunks}
        self._embeddings = embeddings
        self._tokenized_corpus = [tokenize_for_bm25(chunk.text) for chunk in chunks]
        self._bm25 = BM25Plus(self._tokenized_corpus)

    def dense_search(self, query: str, k: int) -> list[SearchHit]:
        if k < 1 or not query.strip():
            return []
        result_count = min(k, MAX_RETRIEVAL_RESULTS, len(self._chunks))
        results = self._collection.query(
            query_embeddings=[self._embeddings.embed_query(query)],
            n_results=result_count,
            include=["distances"],
        )
        ids = results.get("ids", [[]])[0]
        distances = results.get("distances", [[]])[0]
        pairs = sorted(
            zip(ids, distances, strict=True),
            key=lambda pair: (float(pair[1]), pair[0]),
        )
        return [
            SearchHit(
                chunk=self._chunks_by_id[chunk_id],
                rank=rank,
                score=1.0 / (1.0 + max(float(distance), 0.0)),
                retriever="dense",
            )
            for rank, (chunk_id, distance) in enumerate(pairs, start=1)
        ]

    def lexical_search(self, query: str, k: int) -> list[SearchHit]:
        if k < 1:
            return []
        tokens = tokenize_for_bm25(query)
        if not tokens:
            return []
        scores = self._bm25.get_scores(tokens)
        ranked = sorted(
            zip(self._chunks, scores, strict=True),
            key=lambda pair: (-float(pair[1]), pair[0].chunk_id),
        )[: min(k, MAX_RETRIEVAL_RESULTS, len(self._chunks))]
        return [
            SearchHit(
                chunk=chunk,
                rank=rank,
                score=float(score),
                retriever="lexical",
            )
            for rank, (chunk, score) in enumerate(ranked, start=1)
        ]


def load_indexes(index_dir: Path, embeddings: Embeddings) -> HybridIndexes:
    if not index_dir.is_dir():
        raise _not_ready("index directory is missing")
    manifest = _load_manifest(index_dir / "manifest.json")
    chunks = _load_chunks(index_dir / "chunks.json")
    if manifest.chunk_count != len(chunks):
        raise _not_ready("manifest chunk count does not match chunks.json")

    chroma_dir = index_dir / "chroma"
    if not chroma_dir.is_dir():
        raise _not_ready("dense index directory is missing")
    try:
        client = _chroma_client(chroma_dir)
        collection = client.get_collection(COLLECTION_NAME)
        if collection.count() != len(chunks):
            raise _not_ready("dense index count does not match chunks.json")
        stored_ids = collection.get(include=[]).get("ids", [])
        if set(stored_ids) != {chunk.chunk_id for chunk in chunks}:
            raise _not_ready("dense index IDs do not match chunks.json")
    except IndexNotReadyError:
        raise
    except Exception as error:
        raise _not_ready("dense index is missing or corrupt") from error

    return HybridIndexes(
        collection=collection,
        chunks=chunks,
        embeddings=embeddings,
        manifest=manifest,
    )
