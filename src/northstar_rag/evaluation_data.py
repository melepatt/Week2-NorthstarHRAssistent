from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

KNOWN_DOCUMENT_IDS = frozenset(
    {
        "employee-handbook",
        "benefits-guide",
        "leave-and-time-off",
        "remote-work-and-information-security",
        "travel-and-expense",
        "code-of-conduct-and-reporting",
    }
)
KNOWN_CATEGORIES = frozenset({"direct", "cross_document", "ambiguous", "unanswerable"})
FINAL_CATEGORY_COUNTS = {
    "direct": 6,
    "cross_document": 3,
    "ambiguous": 3,
    "unanswerable": 3,
}
REQUIRED_FIELDS = frozenset(
    {
        "id",
        "category",
        "question",
        "answerable",
        "expected_points",
        "expected_document_ids",
        "notes",
    }
)


class EvaluationDataError(ValueError):
    """Raised when an evaluation dataset does not meet its fixed contract."""


@dataclass(frozen=True, slots=True)
class EvaluationQuestion:
    id: str
    category: str
    question: str
    answerable: bool
    expected_points: tuple[str, ...]
    expected_document_ids: tuple[str, ...]
    notes: str


def _text(value: Any, field: str, index: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvaluationDataError(f"record {index} requires nonblank {field}")
    return value.strip()


def _text_tuple(value: Any, field: str, index: int) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise EvaluationDataError(f"record {index} field {field} must be a list")
    items = tuple(_text(item, field, index) for item in value)
    if len(items) != len(set(items)):
        raise EvaluationDataError(f"record {index} field {field} contains duplicates")
    return items


def _decode_record(raw: Any, index: int) -> EvaluationQuestion:
    if not isinstance(raw, dict) or set(raw) != REQUIRED_FIELDS:
        raise EvaluationDataError(f"record {index} must contain exactly the required fields")
    category = _text(raw["category"], "category", index)
    if category not in KNOWN_CATEGORIES:
        raise EvaluationDataError(f"record {index} has unknown category: {category}")
    answerable = raw["answerable"]
    if not isinstance(answerable, bool):
        raise EvaluationDataError(f"record {index} answerable must be a boolean")
    expected_points = _text_tuple(raw["expected_points"], "expected_points", index)
    document_ids = _text_tuple(
        raw["expected_document_ids"],
        "expected_document_ids",
        index,
    )
    unknown_documents = set(document_ids) - KNOWN_DOCUMENT_IDS
    if unknown_documents:
        raise EvaluationDataError(
            f"record {index} has unknown document IDs: {sorted(unknown_documents)}"
        )
    if category == "unanswerable":
        if answerable or expected_points or document_ids:
            raise EvaluationDataError(
                f"record {index} unanswerable items must have no expected points or documents"
            )
    elif not answerable or not expected_points or not document_ids:
        raise EvaluationDataError(
            f"record {index} answerable items require expected points and documents"
        )
    if category == "cross_document" and len(document_ids) < 2:
        raise EvaluationDataError(f"record {index} cross_document items require two documents")

    return EvaluationQuestion(
        id=_text(raw["id"], "id", index),
        category=category,
        question=_text(raw["question"], "question", index),
        answerable=answerable,
        expected_points=expected_points,
        expected_document_ids=document_ids,
        notes=_text(raw["notes"], "notes", index),
    )


def load_evaluation_questions(path: Path) -> list[EvaluationQuestion]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EvaluationDataError(f"unable to read evaluation data: {path}") from error
    if not isinstance(raw, list) or not raw:
        raise EvaluationDataError("evaluation data must be a nonempty JSON list")

    questions = [_decode_record(record, index) for index, record in enumerate(raw, start=1)]
    ids = [question.id for question in questions]
    normalized_text = [" ".join(question.question.casefold().split()) for question in questions]
    if len(ids) != len(set(ids)):
        raise EvaluationDataError("evaluation question IDs must be unique")
    if len(normalized_text) != len(set(normalized_text)):
        raise EvaluationDataError("evaluation question text must be unique")

    if path.name == "development_questions.json" and len(questions) != 5:
        raise EvaluationDataError("development dataset must contain exactly five questions")
    if path.name == "questions.json":
        counts = Counter(question.category for question in questions)
        if len(questions) != 15 or counts != FINAL_CATEGORY_COUNTS:
            raise EvaluationDataError(
                "final dataset size or category counts do not match the fixed evaluation contract"
            )
    return questions
