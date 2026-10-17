from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from northstar_rag.chunking import chunk_pages
from northstar_rag.config import Settings
from northstar_rag.embeddings import NebiusEmbeddings
from northstar_rag.indexes import build_indexes, load_indexes
from northstar_rag.ingestion import load_policy_pages
from northstar_rag.nebius import NebiusGateway, validate_configured_models
from northstar_rag.policy_build import load_manifest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "data" / "source" / "manifest.json"
POLICY_DIR = PROJECT_ROOT / "data" / "policies"
INDEX_DIR = PROJECT_ROOT / "data" / "index"


def _load_corpus_chunks() -> list:
    pages = []
    for entry in load_manifest(MANIFEST_PATH):
        pages.extend(
            load_policy_pages(
                POLICY_DIR / entry.output_file,
                entry.document_id,
                entry.title,
            )
        )
    return chunk_pages(pages)


def _replace_index(temporary_dir: Path, destination: Path) -> None:
    backup = destination.with_name(f".{destination.name}.previous")
    if backup.exists():
        shutil.rmtree(backup)
    had_existing = destination.exists()
    if had_existing:
        os.replace(destination, backup)
    try:
        os.replace(temporary_dir, destination)
    except Exception:
        if had_existing and backup.exists():
            os.replace(backup, destination)
        raise
    if backup.exists():
        shutil.rmtree(backup)


def main() -> None:
    settings = Settings.from_env()
    gateway = NebiusGateway(settings)
    INDEX_DIR.parent.mkdir(parents=True, exist_ok=True)
    temporary_dir = Path(tempfile.mkdtemp(prefix=".index-build-", dir=INDEX_DIR.parent))
    try:
        validate_configured_models(gateway, settings)
        embeddings = NebiusEmbeddings(gateway=gateway, model=settings.embedding_model)
        chunks = _load_corpus_chunks()
        manifest = build_indexes(
            chunks,
            temporary_dir,
            embeddings,
            embedding_model=settings.embedding_model,
        )
        loaded = load_indexes(temporary_dir, embeddings)
        if loaded.manifest != manifest:
            raise RuntimeError("built index failed manifest verification")
        _replace_index(temporary_dir, INDEX_DIR)
        print(f"Indexed {manifest.chunk_count} policy chunks in {INDEX_DIR}")
    finally:
        gateway.close()
        if temporary_dir.exists():
            shutil.rmtree(temporary_dir)


if __name__ == "__main__":
    main()
