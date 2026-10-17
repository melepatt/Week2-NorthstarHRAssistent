from __future__ import annotations

import re

from northstar_rag.chunking import chunk_pages, stable_chunk_id
from northstar_rag.schemas import PolicyPage


def policy_page(
    *,
    document_id: str = "employee-handbook",
    document_title: str = "Employee Handbook",
    page: int = 1,
    text: str,
    section: str = "",
) -> PolicyPage:
    return PolicyPage(
        document_id=document_id,
        document_title=document_title,
        page=page,
        source_path=f"data/policies/{document_id}.pdf",
        text=text,
        section=section,
    )


def tokens(text: str) -> list[str]:
    return re.findall(r"\w+|[^\w\s]", text)


def test_chunks_never_mix_documents_or_pdf_pages() -> None:
    pages = [
        policy_page(text="1. Overview\nHandbook content."),
        policy_page(
            document_id="benefits-guide",
            document_title="Benefits Guide",
            page=2,
            text="2. Eligibility\nBenefits content.",
        ),
    ]

    chunks = chunk_pages(pages)

    assert [(chunk.document_id, chunk.page) for chunk in chunks] == [
        ("employee-handbook", 1),
        ("benefits-guide", 2),
    ]
    assert "Benefits content" not in chunks[0].text
    assert "Handbook content" not in chunks[1].text


def test_chunks_preserve_the_closest_section_heading() -> None:
    page = policy_page(
        text=(
            "1. Benefits\nCoverage begins after eligibility.\n\n"
            "2. Leave\nPaid time off requires approval."
        )
    )

    chunks = chunk_pages([page])

    assert [chunk.section for chunk in chunks] == ["1. Benefits", "2. Leave"]
    assert chunks[0].text.startswith("1. Benefits\n")
    assert chunks[1].text.startswith("2. Leave\n")


def test_oversized_section_uses_600_token_target_and_90_token_overlap() -> None:
    body_tokens = [f"term{index:04d}" for index in range(900)]
    page = policy_page(text="1. Long Section\n" + " ".join(body_tokens))

    chunks = chunk_pages([page], target_tokens=600, overlap_tokens=90)

    assert len(chunks) == 2
    assert all(len(tokens(chunk.text)) <= 600 for chunk in chunks)
    first_body = tokens(chunks[0].text)[4:]
    second_body = tokens(chunks[1].text)[4:]
    assert first_body[-90:] == second_body[:90]


def test_stable_chunk_ids_repeat_and_change_with_provenance() -> None:
    baseline = stable_chunk_id("employee-handbook", 1, "1. Overview", 0)

    assert baseline == stable_chunk_id("employee-handbook", 1, "1.  Overview", 0)
    assert baseline != stable_chunk_id("benefits-guide", 1, "1. Overview", 0)
    assert baseline != stable_chunk_id("employee-handbook", 2, "1. Overview", 0)
    assert baseline != stable_chunk_id("employee-handbook", 1, "2. Eligibility", 0)
    assert baseline != stable_chunk_id("employee-handbook", 1, "1. Overview", 1)
    assert len(baseline) == 20


def test_heading_at_end_of_page_does_not_leak_into_next_page() -> None:
    pages = [
        policy_page(page=1, text="1. Existing\nExisting content.\n\n2. Next Section"),
        policy_page(page=2, text="Continuation text without a heading."),
    ]

    chunks = chunk_pages(pages)

    page_two_chunk = next(chunk for chunk in chunks if chunk.page == 2)
    assert page_two_chunk.section == "Employee Handbook"
    assert "2. Next Section" not in page_two_chunk.text
