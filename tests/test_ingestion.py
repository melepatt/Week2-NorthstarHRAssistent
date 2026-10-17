from __future__ import annotations

import re
from pathlib import Path

import pytest

from northstar_rag.ingestion import IngestionError, load_policy_pages, normalize_page_text
from tests.pdf_fixtures import write_ingestion_fixture

FOOTER_PATTERN = re.compile(r"Page\s+\d+\s+of\s+\d+")


def test_normalize_page_text_removes_only_page_furniture() -> None:
    raw = (
        "Northstar Labs\n"
        "1. Eligibility\n"
        "Full-time\u00a0employees\twork at least 30 hours.\n"
        "4.1 Numbered clauses remain intact.\n"
        "Page 1 of 3\n"
    )

    normalized = normalize_page_text(raw, "Northstar Labs", FOOTER_PATTERN)

    assert normalized == (
        "1. Eligibility\n"
        "Full-time employees work at least 30 hours.\n"
        "4.1 Numbered clauses remain intact."
    )


def test_load_policy_pages_skips_blank_content_pages_and_preserves_pdf_page_numbers(
    tmp_path: Path,
) -> None:
    pdf_path = write_ingestion_fixture(tmp_path / "fixture-policy.pdf")

    pages = load_policy_pages(pdf_path, "fixture-policy", "Fixture Policy")

    assert [page.page for page in pages] == [1, 3]
    assert [page.section for page in pages] == ["1. Eligibility", "2. Leave"]
    assert all(page.document_id == "fixture-policy" for page in pages)
    assert all(page.document_title == "Fixture Policy" for page in pages)
    assert all(page.source_path == str(pdf_path) for page in pages)
    assert all("Northstar Labs" not in page.text for page in pages)
    assert all("Version 2026.10-draft" not in page.text for page in pages)
    assert all("Page " not in page.text for page in pages)


def test_load_policy_pages_names_unreadable_pdf(tmp_path: Path) -> None:
    pdf_path = tmp_path / "unreadable-policy.pdf"
    pdf_path.write_bytes(b"not a PDF")

    with pytest.raises(IngestionError, match=r"unreadable-policy\.pdf"):
        load_policy_pages(pdf_path, "broken", "Broken Policy")


def test_load_policy_pages_rejects_zero_page_document(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "zero-page-policy.pdf"
    pdf_path.write_bytes(b"placeholder")

    class ZeroPageDocument:
        def __enter__(self) -> ZeroPageDocument:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def __len__(self) -> int:
            return 0

    monkeypatch.setattr("northstar_rag.ingestion.pymupdf.open", lambda _: ZeroPageDocument())

    with pytest.raises(IngestionError, match=r"zero-page-policy\.pdf.*zero pages"):
        load_policy_pages(pdf_path, "empty", "Empty Policy")
