from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from northstar_rag.evaluation import (
    FAILURE_CATEGORIES,
    NOT_MEASURED,
    CitationAssessment,
    DevelopmentScore,
    EvaluationRecord,
    EvidenceAssessment,
    FaithfulnessJudgment,
    calculate_metrics,
    calibrate_threshold,
    categorize_failure,
    evaluate_question,
    write_evaluation_outputs,
)
from northstar_rag.evaluation_data import EvaluationQuestion
from northstar_rag.schemas import AnswerResult, ChunkRecord, Citation, SearchHit, StageTiming


def question(
    question_id: str,
    *,
    category: str = "direct",
    answerable: bool = True,
    documents: tuple[str, ...] = ("benefits-guide",),
) -> EvaluationQuestion:
    return EvaluationQuestion(
        id=question_id,
        category=category,
        question="When does coverage begin?",
        answerable=answerable,
        expected_points=("Coverage begins after the waiting period.",) if answerable else (),
        expected_document_ids=documents if answerable else (),
        notes="Metric fixture.",
    )


def evidence(
    document_id: str = "benefits-guide",
    *,
    score: float = 0.8,
) -> EvidenceAssessment:
    return EvidenceAssessment(
        chunk_id=f"{document_id}-chunk",
        document_id=document_id,
        document_title="Benefits Guide",
        page=2,
        rank=1,
        score=score,
        retriever="rerank",
    )


def record(
    question_id: str,
    *,
    category: str,
    answerable: bool,
    refused: bool,
    expected_documents: tuple[str, ...] = (),
    evidence_items: tuple[EvidenceAssessment, ...] = (),
    citations: tuple[CitationAssessment, ...] = (),
    judgment: FaithfulnessJudgment | None = None,
    elapsed_ms: float = 100.0,
    failure_category: str | None = None,
) -> EvaluationRecord:
    return EvaluationRecord(
        question_id=question_id,
        category=category,
        question="Fixture question",
        answer="Fixture answer",
        refused=refused,
        expected_documents=expected_documents,
        retrieved_documents=tuple(dict.fromkeys(item.document_id for item in evidence_items)),
        evidence=evidence_items,
        rerank_scores=tuple(item.score for item in evidence_items),
        citations=citations,
        timings=(StageTiming(stage="end_to_end", elapsed_ms=elapsed_ms),),
        end_to_end_ms=elapsed_ms,
        faithfulness_judgment=judgment,
        manual_review="pending",
        failure_category=failure_category,
        answerable=answerable,
    )


def test_metrics_use_their_specified_denominators_and_nearest_rank_p95() -> None:
    valid_citation = CitationAssessment(
        document_title="Benefits Guide",
        page=2,
        chunk_id="benefits-guide-chunk",
        valid=True,
    )
    invalid_citation = CitationAssessment(
        document_title="Imaginary Policy",
        page=9,
        chunk_id=None,
        valid=False,
    )
    records = [
        record(
            "final-a1",
            category="direct",
            answerable=True,
            refused=False,
            expected_documents=("benefits-guide",),
            evidence_items=(evidence(),),
            citations=(valid_citation,),
            judgment=FaithfulnessJudgment("v1", 2, 2, 1.0, "supported"),
            elapsed_ms=100,
        ),
        record(
            "final-a2",
            category="direct",
            answerable=True,
            refused=True,
            expected_documents=("leave-and-time-off",),
            evidence_items=(evidence("benefits-guide"),),
            elapsed_ms=200,
        ),
        record(
            "final-u1",
            category="unanswerable",
            answerable=False,
            refused=True,
            elapsed_ms=300,
        ),
        record(
            "final-u2",
            category="unanswerable",
            answerable=False,
            refused=False,
            citations=(invalid_citation,),
            judgment=FaithfulnessJudgment("v1", 0, 1, 0.0, "unsupported"),
            elapsed_ms=400,
        ),
    ]

    metrics = calculate_metrics(records)

    assert metrics.retrieval_recall_at_4 == pytest.approx(0.5)
    assert metrics.faithfulness == pytest.approx(2 / 3)
    assert metrics.refusal_accuracy == pytest.approx(0.5)
    assert metrics.citation_validity == pytest.approx(0.5)
    assert metrics.citation_coverage == pytest.approx(0.5)
    assert metrics.latency_p95_ms == pytest.approx(400)


def test_zero_denominators_are_reported_as_not_measured() -> None:
    metrics = calculate_metrics([])

    assert metrics.retrieval_recall_at_4 == NOT_MEASURED
    assert metrics.faithfulness == NOT_MEASURED
    assert metrics.refusal_accuracy == NOT_MEASURED
    assert metrics.citation_validity == NOT_MEASURED
    assert metrics.citation_coverage == NOT_MEASURED
    assert metrics.latency_p95_ms == NOT_MEASURED


class FixedJudge:
    def judge(
        self,
        evaluation_question: EvaluationQuestion,
        result: AnswerResult,
    ) -> FaithfulnessJudgment:
        del evaluation_question, result
        return FaithfulnessJudgment(
            prompt_version="northstar-faithfulness-v1",
            supported_claims=2,
            factual_claims=2,
            raw_score=1.0,
            rationale="All claims are present in the cited evidence.",
        )


def answer_result() -> AnswerResult:
    chunk = ChunkRecord(
        chunk_id="benefits-guide-chunk",
        document_id="benefits-guide",
        document_title="Benefits Guide",
        section="2. Eligibility",
        page=2,
        source_path="benefits.pdf",
        text="Coverage begins after the waiting period.",
    )
    hit = SearchHit(chunk=chunk, rank=1, score=0.88, retriever="rerank")
    return AnswerResult(
        question="When does coverage begin?",
        answer="Coverage begins after the waiting period [Benefits Guide, p. 2].",
        refused=False,
        citations=(Citation("Benefits Guide", 2, "benefits-guide-chunk"),),
        evidence=(hit,),
        timings=(StageTiming("retrieve_dense", 12.0), StageTiming("generate_answer", 18.0)),
    )


def test_evaluate_question_preserves_evidence_scores_timings_and_judgment() -> None:
    item = question("final-direct-benefits")

    evaluated = evaluate_question(item, answer_result(), FixedJudge())

    assert evaluated.expected_documents == ("benefits-guide",)
    assert evaluated.retrieved_documents == ("benefits-guide",)
    assert evaluated.evidence[0].chunk_id == "benefits-guide-chunk"
    assert evaluated.rerank_scores == (0.88,)
    assert evaluated.citations[0].valid is True
    assert evaluated.timings[0].stage == "retrieve_dense"
    assert evaluated.end_to_end_ms == pytest.approx(30.0)
    assert evaluated.faithfulness_judgment is not None
    assert evaluated.faithfulness_judgment.raw_score == 1.0
    assert evaluated.manual_review == "pending"
    assert evaluated.failure_category is None


def test_outputs_contain_complete_records_metrics_and_failure_analysis(tmp_path: Path) -> None:
    failed = record(
        "final-failure",
        category="direct",
        answerable=True,
        refused=True,
        expected_documents=("benefits-guide",),
        evidence_items=(evidence("travel-and-expense", score=0.22),),
        elapsed_ms=125,
        failure_category="fusion/reranking error",
    )
    metrics = calculate_metrics([failed])

    json_path, csv_path, markdown_path = write_evaluation_outputs([failed], metrics, tmp_path)

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["records"][0]["evidence"][0]["chunk_id"] == "travel-and-expense-chunk"
    assert payload["records"][0]["rerank_scores"] == [0.22]
    assert payload["records"][0]["citations"] == []
    assert payload["records"][0]["timings"][0]["elapsed_ms"] == 125
    assert "faithfulness_judgment" in payload["records"][0]
    assert payload["records"][0]["failure_category"] == "fusion/reranking error"
    with csv_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1
    for field in ("evidence", "rerank_scores", "citations", "timings", "faithfulness_judgment"):
        assert field in rows[0]
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "Target" in markdown and "Actual" in markdown
    assert "fusion/reranking error" in markdown
    assert "final-failure" in markdown
    combined = (json_path.read_text() + csv_path.read_text() + markdown).casefold()
    assert "api_key" not in combined
    assert "authorization" not in combined
    assert "super-secret" not in combined


def test_failure_categories_are_limited_to_design_taxonomy() -> None:
    assert {
        "corpus gap",
        "chunking failure",
        "dense retrieval miss",
        "keyword retrieval miss",
        "fusion/reranking error",
        "confidence-gate error",
        "generation error",
        "citation error",
        "ambiguous policy wording",
    } == FAILURE_CATEGORIES
    item = question("final-failure", documents=("benefits-guide",))
    result = AnswerResult(
        question=item.question,
        answer="No answer available.",
        refused=True,
        evidence=(),
        refusal_reason="insufficient_evidence",
    )
    evaluated = record(
        "final-failure",
        category="direct",
        answerable=True,
        refused=True,
    )

    assert categorize_failure(item, result, evaluated) in FAILURE_CATEGORIES


def test_calibration_uses_midpoint_when_development_classes_are_separated() -> None:
    scores = [
        DevelopmentScore("dev-answerable-high", True, 0.9),
        DevelopmentScore("dev-answerable-low", True, 0.55),
        DevelopmentScore("dev-unanswerable-high", False, 0.5),
        DevelopmentScore("dev-unanswerable-low", False, 0.1),
    ]

    assert calibrate_threshold(scores) == pytest.approx(0.525)


def test_calibration_ties_resolve_to_higher_threshold() -> None:
    scores = [
        DevelopmentScore("dev-answerable", True, 0.8),
        DevelopmentScore("dev-unanswerable-high", False, 0.8),
        DevelopmentScore("dev-unanswerable-low", False, 0.2),
    ]

    assert calibrate_threshold(scores) == pytest.approx(0.8)


def test_calibration_rejects_final_set_ids() -> None:
    with pytest.raises(ValueError, match="development"):
        calibrate_threshold(
            [
                DevelopmentScore("dev-answerable", True, 0.8),
                DevelopmentScore("final-unanswerable", False, 0.2),
            ]
        )
