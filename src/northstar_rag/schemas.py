from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any


def _require_text(value: str, name: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} must not be blank")


@dataclass(frozen=True, slots=True)
class PolicyPage:
    document_id: str
    document_title: str
    page: int
    source_path: str
    text: str
    section: str = ""

    def __post_init__(self) -> None:
        _require_text(self.document_id, "document_id")
        _require_text(self.document_title, "document_title")
        _require_text(self.source_path, "source_path")
        _require_text(self.text, "text")
        if self.page < 1:
            raise ValueError("page must be positive")


@dataclass(frozen=True, slots=True)
class ChunkRecord:
    chunk_id: str
    document_id: str
    document_title: str
    section: str
    page: int
    source_path: str
    text: str

    def __post_init__(self) -> None:
        for name in (
            "chunk_id",
            "document_id",
            "document_title",
            "section",
            "source_path",
            "text",
        ):
            _require_text(getattr(self, name), name)
        if self.page < 1:
            raise ValueError("page must be positive")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, values: Mapping[str, Any]) -> ChunkRecord:
        return cls(**dict(values))


@dataclass(frozen=True, slots=True)
class SearchHit:
    chunk: ChunkRecord
    rank: int
    score: float
    retriever: str
    component_ranks: tuple[tuple[str, int], ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.retriever, "retriever")
        if self.rank < 1:
            raise ValueError("rank must be positive")


@dataclass(frozen=True, slots=True)
class Citation:
    document_title: str
    page: int
    chunk_id: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.document_title, "document_title")
        if self.page < 1:
            raise ValueError("page must be positive")


@dataclass(frozen=True, slots=True)
class StageTiming:
    stage: str
    elapsed_ms: float

    def __post_init__(self) -> None:
        _require_text(self.stage, "stage")
        if self.elapsed_ms < 0:
            raise ValueError("elapsed_ms must not be negative")


@dataclass(frozen=True, slots=True)
class AnswerResult:
    question: str
    answer: str
    refused: bool
    citations: tuple[Citation, ...] = ()
    evidence: tuple[SearchHit, ...] = ()
    refusal_reason: str | None = None
    error_code: str | None = None
    timings: tuple[StageTiming, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.question, "question")
        _require_text(self.answer, "answer")
        if self.refused and self.citations:
            raise ValueError("refused answers cannot contain citations")
