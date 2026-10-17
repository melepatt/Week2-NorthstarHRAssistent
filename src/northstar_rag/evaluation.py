from __future__ import annotations

import csv
import json
import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Literal, Protocol

from northstar_rag.evaluation_data import EvaluationQuestion
from northstar_rag.nebius import NebiusGateway, NebiusResponseError
from northstar_rag.schemas import AnswerResult, StageTiming

NOT_MEASURED = "not_measured"
MetricValue = float | Literal["not_measured"]
FAITHFULNESS_PROMPT_VERSION = "northstar-faithfulness-v1"
FAILURE_CATEGORIES = {
    "corpus gap",
    "chunking failure",
    "dense retrieval miss",
    "keyword retrieval miss",
    "fusion/reranking error",
    "confidence-gate error",
    "generation error",
    "citation error",
    "ambiguous policy wording",
}


@dataclass(frozen=True, slots=True)
class EvidenceAssessment:
    chunk_id: str
    document_id: str
    document_title: str
    page: int
    rank: int
    score: float
    retriever: str


@dataclass(frozen=True, slots=True)
class CitationAssessment:
    document_title: str
    page: int
    chunk_id: str | None
    valid: bool


@dataclass(frozen=True, slots=True)
class FaithfulnessJudgment:
    prompt_version: str
    supported_claims: int
    factual_claims: int
    raw_score: float
    rationale: str

    def __post_init__(self) -> None:
        if not self.prompt_version.strip():
            raise ValueError("prompt_version must not be blank")
        if self.supported_claims < 0 or self.factual_claims < 0:
            raise ValueError("claim counts must not be negative")
        if self.supported_claims > self.factual_claims:
            raise ValueError("supported_claims cannot exceed factual_claims")
        if not 0.0 <= self.raw_score <= 1.0:
            raise ValueError("raw_score must be between zero and one")


@dataclass(frozen=True, slots=True)
class EvaluationRecord:
    question_id: str
    category: str
    question: str
    answer: str
    refused: bool
    expected_documents: tuple[str, ...]
    retrieved_documents: tuple[str, ...]
    evidence: tuple[EvidenceAssessment, ...]
    rerank_scores: tuple[float, ...]
    citations: tuple[CitationAssessment, ...]
    timings: tuple[StageTiming, ...]
    end_to_end_ms: float
    faithfulness_judgment: FaithfulnessJudgment | None
    manual_review: str
    failure_category: str | None
    answerable: bool

    def __post_init__(self) -> None:
        if self.failure_category is not None and self.failure_category not in FAILURE_CATEGORIES:
            raise ValueError(f"unknown failure category: {self.failure_category}")
        if self.end_to_end_ms < 0:
            raise ValueError("end_to_end_ms must not be negative")


@dataclass(frozen=True, slots=True)
class EvaluationMetrics:
    retrieval_recall_at_4: MetricValue
    faithfulness: MetricValue
    refusal_accuracy: MetricValue
    citation_validity: MetricValue
    citation_coverage: MetricValue
    latency_p95_ms: MetricValue


@dataclass(frozen=True, slots=True)
class DevelopmentScore:
    question_id: str
    answerable: bool
    highest_score: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.highest_score <= 1.0:
            raise ValueError("highest_score must be between zero and one")


class FaithfulnessJudge(Protocol):
    def judge(
        self,
        question: EvaluationQuestion,
        result: AnswerResult,
    ) -> FaithfulnessJudgment: ...


@dataclass(slots=True)
class NebiusFaithfulnessJudge:
    gateway: NebiusGateway
    model: str

    def judge(
        self,
        question: EvaluationQuestion,
        result: AnswerResult,
    ) -> FaithfulnessJudgment:
        evidence = "\n\n".join(
            f"{hit.chunk.document_title}, p. {hit.chunk.page}:\n{hit.chunk.text}"
            for hit in result.evidence
        )
        system = (
            "Evaluate whether each factual claim in the answer is supported by the supplied "
            "policy evidence. Return only JSON with integer supported_claims, integer "
            "factual_claims, numeric raw_score from 0 to 1, and a short rationale."
        )
        user = (
            f"Prompt version: {FAITHFULNESS_PROMPT_VERSION}\n"
            f"Question: {question.question}\n"
            f"Answer: {result.answer}\n"
            f"Evidence:\n{evidence}"
        )
        raw = self.gateway.complete(system, user, self.model)
        try:
            payload = json.loads(raw)
            return FaithfulnessJudgment(
                prompt_version=FAITHFULNESS_PROMPT_VERSION,
                supported_claims=int(payload["supported_claims"]),
                factual_claims=int(payload["factual_claims"]),
                raw_score=float(payload["raw_score"]),
                rationale=str(payload["rationale"]),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise NebiusResponseError("faithfulness judge returned an invalid decision") from error


def _assess_evidence(result: AnswerResult) -> tuple[EvidenceAssessment, ...]:
    return tuple(
        EvidenceAssessment(
            chunk_id=hit.chunk.chunk_id,
            document_id=hit.chunk.document_id,
            document_title=hit.chunk.document_title,
            page=hit.chunk.page,
            rank=hit.rank,
            score=hit.score,
            retriever=hit.retriever,
        )
        for hit in result.evidence
    )


def _assess_citations(result: AnswerResult) -> tuple[CitationAssessment, ...]:
    assessments: list[CitationAssessment] = []
    for citation in result.citations:
        matching = [
            hit
            for hit in result.evidence
            if hit.chunk.document_title == citation.document_title
            and hit.chunk.page == citation.page
        ]
        valid = bool(matching) and (
            citation.chunk_id is None
            or any(hit.chunk.chunk_id == citation.chunk_id for hit in matching)
        )
        assessments.append(
            CitationAssessment(
                document_title=citation.document_title,
                page=citation.page,
                chunk_id=citation.chunk_id,
                valid=valid,
            )
        )
    return tuple(assessments)


def evaluate_question(
    question: EvaluationQuestion,
    result: AnswerResult,
    judge: FaithfulnessJudge,
) -> EvaluationRecord:
    evidence = _assess_evidence(result)
    citations = _assess_citations(result)
    judgment = None if result.refused else judge.judge(question, result)
    record = EvaluationRecord(
        question_id=question.id,
        category=question.category,
        question=question.question,
        answer=result.answer,
        refused=result.refused,
        expected_documents=question.expected_document_ids,
        retrieved_documents=tuple(dict.fromkeys(item.document_id for item in evidence)),
        evidence=evidence,
        rerank_scores=tuple(item.score for item in evidence),
        citations=citations,
        timings=result.timings,
        end_to_end_ms=sum(timing.elapsed_ms for timing in result.timings),
        faithfulness_judgment=judgment,
        manual_review="pending",
        failure_category=None,
        answerable=question.answerable,
    )
    return replace(
        record,
        failure_category=categorize_failure(question, result, record),
    )


def categorize_failure(
    question: EvaluationQuestion,
    result: AnswerResult,
    record: EvaluationRecord,
) -> str | None:
    if not question.answerable:
        return None if result.refused else "confidence-gate error"
    if result.refused:
        if not record.evidence:
            return "corpus gap"
        if not set(question.expected_document_ids) & set(record.retrieved_documents):
            return "fusion/reranking error"
        return "confidence-gate error"
    if not record.citations or any(not citation.valid for citation in record.citations):
        return "citation error"
    judgment = record.faithfulness_judgment
    if judgment is not None and judgment.supported_claims < judgment.factual_claims:
        return "generation error"
    return None


def _ratio(numerator: int, denominator: int) -> MetricValue:
    return numerator / denominator if denominator else NOT_MEASURED


def calculate_metrics(records: Sequence[EvaluationRecord]) -> EvaluationMetrics:
    answerable = [record for record in records if record.answerable]
    retrieved = sum(
        bool(set(record.expected_documents) & {item.document_id for item in record.evidence[:4]})
        for record in answerable
    )

    judgments = [
        record.faithfulness_judgment
        for record in records
        if record.faithfulness_judgment is not None
    ]
    supported_claims = sum(judgment.supported_claims for judgment in judgments)
    factual_claims = sum(judgment.factual_claims for judgment in judgments)

    unanswerable = [record for record in records if not record.answerable]
    correct_refusals = sum(record.refused for record in unanswerable)

    citations = [citation for record in records for citation in record.citations]
    valid_citations = sum(citation.valid for citation in citations)

    answered = [record for record in records if not record.refused]
    covered = sum(any(citation.valid for citation in record.citations) for record in answered)

    latencies = sorted(record.end_to_end_ms for record in records)
    if latencies:
        nearest_rank_index = max(math.ceil(0.95 * len(latencies)) - 1, 0)
        latency_p95: MetricValue = latencies[nearest_rank_index]
    else:
        latency_p95 = NOT_MEASURED

    return EvaluationMetrics(
        retrieval_recall_at_4=_ratio(retrieved, len(answerable)),
        faithfulness=_ratio(supported_claims, factual_claims),
        refusal_accuracy=_ratio(correct_refusals, len(unanswerable)),
        citation_validity=_ratio(valid_citations, len(citations)),
        citation_coverage=_ratio(covered, len(answered)),
        latency_p95_ms=latency_p95,
    )


def _format_metric(value: MetricValue, *, milliseconds: bool = False) -> str:
    if value == NOT_MEASURED:
        return NOT_MEASURED
    if milliseconds:
        return f"{value:.1f} ms"
    return f"{value:.1%}"


def _record_payload(record: EvaluationRecord) -> dict:
    return asdict(record)


def write_evaluation_outputs(
    records: Sequence[EvaluationRecord],
    metrics: EvaluationMetrics,
    output_dir: Path,
) -> tuple[Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "evaluation.json"
    csv_path = output_dir / "evaluation.csv"
    markdown_path = output_dir / "evaluation-report.md"

    record_payloads = [_record_payload(record) for record in records]
    json_path.write_text(
        json.dumps(
            {"metrics": asdict(metrics), "records": record_payloads},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    scalar_fields = [
        "question_id",
        "category",
        "question",
        "answer",
        "refused",
        "answerable",
        "end_to_end_ms",
        "manual_review",
        "failure_category",
    ]
    nested_fields = [
        "expected_documents",
        "retrieved_documents",
        "evidence",
        "rerank_scores",
        "citations",
        "timings",
        "faithfulness_judgment",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=scalar_fields + nested_fields)
        writer.writeheader()
        for payload in record_payloads:
            row = {field: payload[field] for field in scalar_fields}
            row.update(
                {field: json.dumps(payload[field], sort_keys=True) for field in nested_fields}
            )
            writer.writerow(row)

    metric_rows = [
        ("Retrieval recall@4", ">= 85%", _format_metric(metrics.retrieval_recall_at_4)),
        ("Faithfulness", ">= 95%", _format_metric(metrics.faithfulness)),
        ("Refusal accuracy", "100%", _format_metric(metrics.refusal_accuracy)),
        ("Citation validity", "100%", _format_metric(metrics.citation_validity)),
        ("Citation coverage", "100%", _format_metric(metrics.citation_coverage)),
        (
            "End-to-end p95 latency",
            "<= 8000 ms",
            _format_metric(metrics.latency_p95_ms, milliseconds=True),
        ),
    ]
    lines = [
        "# Northstar HR Policy Assistant Evaluation",
        "",
        "## Metrics",
        "",
        "| Measure | Target | Actual |",
        "| --- | ---: | ---: |",
        *(f"| {name} | {target} | {actual} |" for name, target, actual in metric_rows),
        "",
        "## Per-question results",
        "",
        "| Question ID | Outcome | Retrieved evidence | Failure category |",
        "| --- | --- | --- | --- |",
    ]
    for record in records:
        evidence_text = (
            ", ".join(
                f"{item.document_title} p. {item.page} ({item.score:.3f})"
                for item in record.evidence
            )
            or "None"
        )
        outcome = "Refused" if record.refused else "Answered"
        lines.append(
            f"| {record.question_id} | {outcome} | {evidence_text} | "
            f"{record.failure_category or 'None'} |"
        )
    failures = [record for record in records if record.failure_category]
    lines.extend(["", "## Failures", ""])
    if failures:
        lines.extend(f"- `{record.question_id}`: {record.failure_category}" for record in failures)
    else:
        lines.append("No failures were recorded.")
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, csv_path, markdown_path


def calibrate_threshold(records: Sequence[DevelopmentScore]) -> float:
    if not records or any(not record.question_id.startswith("dev-") for record in records):
        raise ValueError("threshold calibration accepts development records only")
    answerable = [record for record in records if record.answerable]
    unanswerable = [record for record in records if not record.answerable]
    if not answerable or not unanswerable:
        raise ValueError("threshold calibration requires both development classes")

    lowest_answerable = min(record.highest_score for record in answerable)
    highest_unanswerable = max(record.highest_score for record in unanswerable)
    if highest_unanswerable < lowest_answerable:
        return (highest_unanswerable + lowest_answerable) / 2.0

    candidates = {0.0, 1.0, *(record.highest_score for record in records)}
    scored: list[tuple[float, float]] = []
    for threshold in candidates:
        answer_accuracy = sum(record.highest_score >= threshold for record in answerable) / len(
            answerable
        )
        refusal_accuracy = sum(record.highest_score < threshold for record in unanswerable) / len(
            unanswerable
        )
        scored.append(((answer_accuracy + refusal_accuracy) / 2.0, threshold))
    return max(scored)[1]
