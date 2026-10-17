from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from northstar_rag.indexes import IndexNotReadyError, build_indexes, load_indexes
from northstar_rag.schemas import ChunkRecord
from tests.fakes import DeterministicEmbeddings


def make_chunks(source_path: Path) -> list[ChunkRecord]:
    return [
        ChunkRecord(
            chunk_id="chunk-b",
            document_id="security",
            document_title="Security Policy",
            section="2. Devices",
            page=2,
            source_path=str(source_path),
            text="Company laptops require encryption and prompt security updates.",
        ),
        ChunkRecord(
            chunk_id="chunk-a",
            document_id="leave",
            document_title="Leave Policy",
            section="1. Vacation",
            page=1,
            source_path=str(source_path),
            text="Employees receive vacation leave after manager approval.",
        ),
    ]


def test_build_persists_canonical_chunks_manifest_and_dense_index(tmp_path: Path) -> None:
    source_path = tmp_path / "policy.pdf"
    source_path.write_bytes(b"controlled policy fixture")
    index_dir = tmp_path / "index"

    manifest = build_indexes(
        make_chunks(source_path),
        index_dir,
        DeterministicEmbeddings(),
        embedding_model="fixture-embedding-v1",
    )

    assert (index_dir / "chroma" / "chroma.sqlite3").is_file()
    assert (index_dir / "chunks.json").is_file()
    assert (index_dir / "manifest.json").is_file()
    chunk_data = json.loads((index_dir / "chunks.json").read_text(encoding="utf-8"))
    assert [item["chunk_id"] for item in chunk_data] == ["chunk-a", "chunk-b"]
    assert manifest.schema_version == 1
    assert manifest.embedding_model == "fixture-embedding-v1"
    assert manifest.chunk_count == 2
    assert manifest.source_hashes == {
        str(source_path): hashlib.sha256(source_path.read_bytes()).hexdigest()
    }
    assert json.loads((index_dir / "manifest.json").read_text(encoding="utf-8")) == {
        "chunk_count": 2,
        "embedding_model": "fixture-embedding-v1",
        "schema_version": 1,
        "source_hashes": manifest.source_hashes,
    }


def test_reload_reconstructs_dense_and_lexical_indexes(tmp_path: Path) -> None:
    source_path = tmp_path / "policy.pdf"
    source_path.write_bytes(b"controlled policy fixture")
    index_dir = tmp_path / "index"
    embeddings = DeterministicEmbeddings()
    build_indexes(
        make_chunks(source_path),
        index_dir,
        embeddings,
        embedding_model="fixture-embedding-v1",
    )

    first = load_indexes(index_dir, embeddings)
    reloaded = load_indexes(index_dir, embeddings)

    assert [hit.chunk.chunk_id for hit in first.dense_search("vacation leave", 8)] == [
        hit.chunk.chunk_id for hit in reloaded.dense_search("vacation leave", 8)
    ]
    assert [hit.chunk.chunk_id for hit in first.lexical_search("vacation leave", 8)] == [
        hit.chunk.chunk_id for hit in reloaded.lexical_search("vacation leave", 8)
    ]
    assert reloaded.lexical_search("vacation leave", 8)[0].chunk.chunk_id == "chunk-a"


@pytest.mark.parametrize("state", ["missing", "empty", "corrupt"])
def test_load_rejects_unready_index_with_operator_instruction(
    tmp_path: Path,
    state: str,
) -> None:
    index_dir = tmp_path / "index"
    if state == "empty":
        index_dir.mkdir()
    elif state == "corrupt":
        index_dir.mkdir()
        (index_dir / "chunks.json").write_text("not json", encoding="utf-8")
        (index_dir / "manifest.json").write_text("{}", encoding="utf-8")
        (index_dir / "chroma").mkdir()

    with pytest.raises(IndexNotReadyError, match=r"python scripts/ingest\.py"):
        load_indexes(index_dir, DeterministicEmbeddings())


def test_build_rejects_empty_chunk_collection(tmp_path: Path) -> None:
    with pytest.raises(IndexNotReadyError, match=r"python scripts/ingest\.py"):
        build_indexes([], tmp_path / "index", DeterministicEmbeddings(), embedding_model="model")


def test_build_supports_the_public_three_argument_interface(tmp_path: Path) -> None:
    source_path = tmp_path / "policy.pdf"
    source_path.write_bytes(b"controlled policy fixture")

    manifest = build_indexes(
        make_chunks(source_path),
        tmp_path / "index",
        DeterministicEmbeddings(),
    )

    assert manifest.embedding_model == "DeterministicEmbeddings"
