from __future__ import annotations

from northstar_rag.citations import parse_citations, validate_grounded_answer
from northstar_rag.schemas import ChunkRecord, SearchHit


def evidence_hit(title: str, page: int, chunk_id: str) -> SearchHit:
    return SearchHit(
        chunk=ChunkRecord(
            chunk_id=chunk_id,
            document_id=chunk_id.split("-")[0],
            document_title=title,
            section="1. Scope",
            page=page,
            source_path="data/policies/policy.pdf",
            text="Controlled policy evidence.",
        ),
        rank=1,
        score=0.9,
        retriever="rerank",
    )


def test_parse_citations_preserves_display_order_and_deduplicates() -> None:
    answer = (
        "See [Benefits Guide, p. 3], then [Employee Handbook, p. 1]. "
        "The first source also applies [Benefits Guide, p. 3]."
    )

    citations = parse_citations(answer)

    assert [(item.document_title, item.page) for item in citations] == [
        ("Benefits Guide", 3),
        ("Employee Handbook", 1),
    ]


def test_exact_retrieved_title_and_page_pass_with_ordinary_brackets() -> None:
    evidence = [evidence_hit("Benefits Guide", 3, "benefits-3")]

    result = validate_grounded_answer(
        "Enrollment [when applicable] must occur within the stated window [Benefits Guide, p. 3].",
        evidence,
    )

    assert result.valid is True
    assert result.reason is None
    assert [(item.document_title, item.page) for item in result.citations] == [
        ("Benefits Guide", 3)
    ]


def test_unknown_title_fails_validation() -> None:
    result = validate_grounded_answer(
        "The benefit applies [Unknown Policy, p. 3].",
        [evidence_hit("Benefits Guide", 3, "benefits-3")],
    )

    assert result.valid is False
    assert result.citations == ()
    assert "not retrieved" in (result.reason or "")


def test_title_match_is_case_sensitive() -> None:
    result = validate_grounded_answer(
        "The benefit applies [benefits guide, p. 3].",
        [evidence_hit("Benefits Guide", 3, "benefits-3")],
    )

    assert result.valid is False


def test_unretrieved_page_of_retrieved_document_fails_validation() -> None:
    result = validate_grounded_answer(
        "The benefit applies [Benefits Guide, p. 2].",
        [evidence_hit("Benefits Guide", 3, "benefits-3")],
    )

    assert result.valid is False
    assert "not retrieved" in (result.reason or "")


def test_invalid_or_malformed_page_citation_fails_validation() -> None:
    evidence = [evidence_hit("Benefits Guide", 3, "benefits-3")]

    zero_page = validate_grounded_answer("See [Benefits Guide, p. 0].", evidence)
    text_page = validate_grounded_answer("See [Benefits Guide, p. three].", evidence)
    missing_comma = validate_grounded_answer("See [Benefits Guide p. 3].", evidence)

    assert zero_page.valid is False
    assert text_page.valid is False
    assert missing_comma.valid is False
    assert "malformed" in (zero_page.reason or "")
    assert "malformed" in (text_page.reason or "")
    assert "malformed" in (missing_comma.reason or "")


def test_non_refusal_answer_without_citation_fails_validation() -> None:
    result = validate_grounded_answer(
        "Employees may enroll after a qualifying event.",
        [evidence_hit("Benefits Guide", 3, "benefits-3")],
    )

    assert result.valid is False
    assert "at least one" in (result.reason or "")


def test_unmatched_citation_bracket_fails_validation() -> None:
    missing_close = validate_grounded_answer(
        "Employees may enroll [Benefits Guide, p. 3.",
        [evidence_hit("Benefits Guide", 3, "benefits-3")],
    )
    extra_close = validate_grounded_answer(
        "Employees may enroll [Benefits Guide, p. 3]].",
        [evidence_hit("Benefits Guide", 3, "benefits-3")],
    )

    assert missing_close.valid is False
    assert extra_close.valid is False
    assert "malformed" in (missing_close.reason or "")
    assert "malformed" in (extra_close.reason or "")


def test_valid_citations_are_linked_to_matching_chunk_ids() -> None:
    evidence = [
        evidence_hit("Benefits Guide", 3, "benefits-3-a"),
        evidence_hit("Benefits Guide", 3, "benefits-3-b"),
    ]

    result = validate_grounded_answer("See [Benefits Guide, p. 3].", evidence)

    assert result.valid is True
    assert result.citations[0].chunk_id == "benefits-3-a"
