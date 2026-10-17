from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from northstar_rag.schemas import AnswerResult, ChunkRecord, Citation, PolicyPage


def make_chunk() -> ChunkRecord:
    return ChunkRecord(
        chunk_id="employee-handbook-p1-overview-0001",
        document_id="employee-handbook",
        document_title="Employee Handbook",
        section="Company Overview",
        page=1,
        source_path="data/policies/employee-handbook.pdf",
        text="Northstar Labs is a remote-first company.",
    )


def test_chunk_record_round_trips_through_plain_dictionary() -> None:
    chunk = make_chunk()

    assert ChunkRecord.from_dict(chunk.to_dict()) == chunk


@pytest.mark.parametrize("record_type", [PolicyPage, ChunkRecord])
def test_page_based_records_reject_nonpositive_page_numbers(record_type: type) -> None:
    values = {
        "document_id": "employee-handbook",
        "document_title": "Employee Handbook",
        "page": 0,
        "source_path": "data/policies/employee-handbook.pdf",
        "text": "Policy text",
    }
    if record_type is ChunkRecord:
        values.update(chunk_id="chunk-1", section="Overview")

    with pytest.raises(ValueError, match="page must be positive"):
        record_type(**values)


def test_domain_records_are_immutable() -> None:
    chunk = make_chunk()

    with pytest.raises(FrozenInstanceError):
        chunk.text = "changed"  # type: ignore[misc]


def test_refusal_cannot_expose_citations() -> None:
    citation = Citation(
        document_title="Employee Handbook",
        page=1,
        chunk_id="employee-handbook-p1-overview-0001",
    )

    with pytest.raises(ValueError, match="refused answers cannot contain citations"):
        AnswerResult(
            question="What is the company overview?",
            answer="I could not find an answer.",
            refused=True,
            citations=(citation,),
            evidence=(),
            refusal_reason="insufficient_evidence",
        )
