from __future__ import annotations

import argparse
import shutil
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from northstar_rag.config import Settings
from northstar_rag.evaluation import (
    DevelopmentScore,
    NebiusFaithfulnessJudge,
    calculate_metrics,
    calibrate_threshold,
    evaluate_question,
    write_evaluation_outputs,
)
from northstar_rag.evaluation_data import load_evaluation_questions
from northstar_rag.graph import answer_question
from northstar_rag.nebius import NebiusGateway

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVALUATION_DIR = PROJECT_ROOT / "evaluation"
STABLE_REPORT = PROJECT_ROOT / "docs" / "evaluation-report.md"


def _threshold(value: str) -> float:
    try:
        threshold = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("threshold must be a number") from error
    if not 0.0 <= threshold <= 1.0:
        raise argparse.ArgumentTypeError("threshold must be between zero and one")
    return threshold


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate the Northstar HR policy assistant")
    parser.add_argument(
        "--dataset",
        choices=("development", "final"),
        default="final",
        help="fixed evaluation partition to run",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=EVALUATION_DIR / "runs",
        help="parent directory for timestamped evaluation artifacts",
    )
    parser.add_argument(
        "--threshold",
        type=_threshold,
        help="evidence threshold for this run; defaults to RERANK_MIN_SCORE",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    settings = Settings.from_env()
    if args.threshold is not None:
        settings = replace(settings, rerank_min_score=args.threshold)

    # Runtime assembly is shared with the employee application and imported lazily so
    # dataset/report tooling remains usable without initializing provider clients.
    from northstar_rag.runtime import create_runtime

    graph = create_runtime(settings)
    gateway = NebiusGateway(settings)
    judge = NebiusFaithfulnessJudge(gateway=gateway, model=settings.chat_model)
    dataset_name = (
        "development_questions.json" if args.dataset == "development" else "questions.json"
    )
    questions = load_evaluation_questions(EVALUATION_DIR / dataset_name)
    try:
        records = [
            evaluate_question(question, answer_question(graph, question.question), judge)
            for question in questions
        ]
    finally:
        gateway.close()

    metrics = calculate_metrics(records)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = args.output_dir / f"{timestamp}-{args.dataset}"
    json_path, csv_path, report_path = write_evaluation_outputs(records, metrics, run_dir)
    STABLE_REPORT.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(report_path, STABLE_REPORT)

    print(f"JSON: {json_path}")
    print(f"CSV: {csv_path}")
    print(f"Report: {report_path}")
    if args.dataset == "development":
        development_scores = [
            DevelopmentScore(
                question_id=record.question_id,
                answerable=record.answerable,
                highest_score=max(record.rerank_scores, default=0.0),
            )
            for record in records
        ]
        calibrated = calibrate_threshold(development_scores)
        print(f"Calibrated development threshold: {calibrated:.3f}")


if __name__ == "__main__":
    main()
