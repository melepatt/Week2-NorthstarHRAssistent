from __future__ import annotations

import json
from pathlib import Path

import pymupdf
import pytest

from northstar_rag.policy_build import PolicyBuildError, build_corpus, load_manifest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "data" / "source" / "manifest.json"

EXPECTED_FILES = [
    "employee-handbook.pdf",
    "benefits-guide.pdf",
    "leave-and-time-off.pdf",
    "remote-work-and-information-security.pdf",
    "travel-and-expense.pdf",
    "code-of-conduct-and-reporting.pdf",
]


def extracted_pages(path: Path) -> list[str]:
    with pymupdf.open(path) as document:
        return [page.get_text("text") for page in document]


def test_build_corpus_creates_six_pdfs_in_manifest_order(tmp_path: Path) -> None:
    entries = load_manifest(MANIFEST_PATH)

    outputs = build_corpus(MANIFEST_PATH, tmp_path)

    assert [path.name for path in outputs] == EXPECTED_FILES
    assert [entry.output_file.name for entry in entries] == EXPECTED_FILES
    assert all(path.is_file() for path in outputs)


def test_rebuild_has_stable_page_text_and_page_count(tmp_path: Path) -> None:
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"

    first = build_corpus(MANIFEST_PATH, first_dir)
    second = build_corpus(MANIFEST_PATH, second_dir)

    assert [extracted_pages(path) for path in first] == [extracted_pages(path) for path in second]
    assert [len(extracted_pages(path)) for path in first] == [
        len(extracted_pages(path)) for path in second
    ]


def test_every_pdf_page_contains_company_furniture(tmp_path: Path) -> None:
    entries = load_manifest(MANIFEST_PATH)
    outputs = build_corpus(MANIFEST_PATH, tmp_path)

    for entry, output in zip(entries, outputs, strict=True):
        pages = extracted_pages(output)
        assert pages
        for page_number, text in enumerate(pages, start=1):
            assert "Northstar Labs" in text
            assert entry.title in text
            assert f"Version {entry.version}" in text
            assert f"Page {page_number} of {len(pages)}" in text


def test_first_page_separates_draft_status_from_policy_metadata(tmp_path: Path) -> None:
    output = build_corpus(MANIFEST_PATH, tmp_path)[0]
    first_page = extracted_pages(output)[0]

    assert "Internal draft - approval required before employee use" in first_page
    assert "Effective date: Pending approval\nPolicy owner: People Operations" in first_page
    assert "—" not in first_page


def test_load_manifest_rejects_missing_source(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            [
                {
                    "document_id": "missing-policy",
                    "title": "Missing Policy",
                    "source_file": "missing.md",
                    "output_file": "missing.pdf",
                    "version": "2026.10-draft",
                }
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(PolicyBuildError, match=r"missing-policy.*missing\.md"):
        load_manifest(manifest)


def test_load_manifest_rejects_duplicate_document_ids(tmp_path: Path) -> None:
    (tmp_path / "one.md").write_text("# One\n", encoding="utf-8")
    (tmp_path / "two.md").write_text("# Two\n", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            [
                {
                    "document_id": "duplicate-policy",
                    "title": "One",
                    "source_file": "one.md",
                    "output_file": "one.pdf",
                    "version": "2026.10-draft",
                },
                {
                    "document_id": "duplicate-policy",
                    "title": "Two",
                    "source_file": "two.md",
                    "output_file": "two.pdf",
                    "version": "2026.10-draft",
                },
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(PolicyBuildError, match="duplicate document_id: duplicate-policy"):
        load_manifest(manifest)
