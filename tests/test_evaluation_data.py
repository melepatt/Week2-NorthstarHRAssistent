from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from northstar_rag.evaluation_data import (
    KNOWN_DOCUMENT_IDS,
    EvaluationDataError,
    load_evaluation_questions,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEVELOPMENT_PATH = PROJECT_ROOT / "evaluation" / "development_questions.json"
FINAL_PATH = PROJECT_ROOT / "evaluation" / "questions.json"
FINAL_MANUAL_REVIEW_PATH = PROJECT_ROOT / "evaluation" / "final_manual_reviews.json"


def test_fixed_datasets_have_required_sizes_categories_and_no_overlap() -> None:
    development = load_evaluation_questions(DEVELOPMENT_PATH)
    final = load_evaluation_questions(FINAL_PATH)

    assert len(development) == 5
    assert len(final) == 15
    assert Counter(item.category for item in final) == {
        "direct": 6,
        "cross_document": 3,
        "ambiguous": 3,
        "unanswerable": 3,
    }
    all_ids = [item.id for item in development + final]
    all_questions = [item.question.casefold() for item in development + final]
    assert len(all_ids) == len(set(all_ids))
    assert len(all_questions) == len(set(all_questions))


def test_records_have_nonblank_fields_and_known_expected_documents() -> None:
    records = load_evaluation_questions(DEVELOPMENT_PATH) + load_evaluation_questions(FINAL_PATH)

    for item in records:
        assert item.id.strip()
        assert item.question.strip()
        assert item.notes.strip()
        assert all(point.strip() for point in item.expected_points)
        assert set(item.expected_document_ids) <= KNOWN_DOCUMENT_IDS
        if item.answerable:
            assert item.expected_points
            assert item.expected_document_ids
        else:
            assert item.category == "unanswerable"
            assert item.expected_points == ()
            assert item.expected_document_ids == ()


def test_cross_document_and_ambiguous_records_encode_required_qualifications() -> None:
    final = load_evaluation_questions(FINAL_PATH)

    for item in final:
        if item.category == "cross_document":
            assert len(item.expected_document_ids) >= 2
        if item.category == "ambiguous":
            combined = " ".join(item.expected_points).casefold()
            assert any(word in combined for word in ("requires", "depends", "must identify"))


def test_final_manual_review_covers_every_fixed_question_without_pending_status() -> None:
    final = load_evaluation_questions(FINAL_PATH)
    reviews = json.loads(FINAL_MANUAL_REVIEW_PATH.read_text(encoding="utf-8"))

    assert {review["question_id"] for review in reviews} == {item.id for item in final}
    assert len(reviews) == len(final)
    assert all(review["status"] in {"pass", "partial", "fail"} for review in reviews)
    assert all(review["notes"].strip() for review in reviews)


def valid_record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "id": "dev-01",
        "category": "direct",
        "question": "When does coverage begin?",
        "answerable": True,
        "expected_points": ["Coverage generally begins after the waiting period."],
        "expected_document_ids": ["benefits-guide"],
        "notes": "Checks the coverage-start rule.",
    }
    record.update(overrides)
    return record


def write_data(path: Path, records: list[dict[str, object]]) -> Path:
    path.write_text(json.dumps(records), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "records",
    [
        [valid_record(category="unsupported")],
        [valid_record(), valid_record(question="A different question")],
        [valid_record(), valid_record(id="dev-02", question="WHEN DOES COVERAGE BEGIN?")],
        [valid_record(expected_document_ids=["unknown-policy"])],
        [valid_record(answerable=False)],
        [
            valid_record(
                category="unanswerable",
                answerable=False,
                expected_points=["Should not be present"],
                expected_document_ids=[],
            )
        ],
        [
            valid_record(
                category="unanswerable",
                answerable=True,
                expected_points=["Contradiction"],
                expected_document_ids=["benefits-guide"],
            )
        ],
    ],
)
def test_loader_rejects_schema_and_answerability_contradictions(
    tmp_path: Path,
    records: list[dict[str, object]],
) -> None:
    path = write_data(tmp_path / "custom.json", records)

    with pytest.raises(EvaluationDataError):
        load_evaluation_questions(path)


def test_loader_rejects_final_category_count_drift(tmp_path: Path) -> None:
    records = [
        valid_record(id=f"final-{number:02d}", question=f"Question {number}")
        for number in range(15)
    ]
    path = write_data(tmp_path / "questions.json", records)

    with pytest.raises(EvaluationDataError, match="category counts"):
        load_evaluation_questions(path)


def test_loader_rejects_invalid_json_and_nonlist_root(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.json"
    invalid.write_text("not-json", encoding="utf-8")
    nonlist = tmp_path / "nonlist.json"
    nonlist.write_text("{}", encoding="utf-8")

    with pytest.raises(EvaluationDataError):
        load_evaluation_questions(invalid)
    with pytest.raises(EvaluationDataError):
        load_evaluation_questions(nonlist)
