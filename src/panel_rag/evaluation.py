from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from .bootstrap import build_service
from .models import EvaluationResult
from .service import RAGService


def load_dataset(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("評価データはJSON配列で指定してください。")
    return payload


def evaluate(service: RAGService, cases: list[dict]) -> list[EvaluationResult]:
    results: list[EvaluationResult] = []
    for case in cases:
        response = service.ask(case["question"])
        expected_sources = set(case.get("expected_sources", []))
        actual_sources = {item.hit.file_name for item in response.citations}
        if expected_sources:
            source_recall = len(expected_sources & actual_sources) / len(expected_sources)
        else:
            source_recall = 1.0 if not response.answerable else 0.0

        expected_terms = [str(item).lower() for item in case.get("expected_terms", [])]
        if expected_terms and response.answerable:
            answer_lower = response.answer.lower()
            term_coverage = sum(term in answer_lower for term in expected_terms) / len(
                expected_terms
            )
        elif expected_terms:
            term_coverage = 0.0
        else:
            term_coverage = None

        answerability_correct = (
            response.answerable is bool(case["expected_answerable"])
        )
        passed = answerability_correct and source_recall == 1.0
        results.append(
            EvaluationResult(
                case_id=str(case["id"]),
                question=str(case["question"]),
                categories=[str(item) for item in case["categories"]],
                expected_answerable=bool(case["expected_answerable"]),
                actual_answerable=response.answerable,
                answerability_correct=answerability_correct,
                source_recall=source_recall,
                term_coverage=term_coverage,
                passed=passed,
                answer=response.answer,
                retrieved_sources=sorted(actual_sources),
            )
        )
    return results


def summarize(results: list[EvaluationResult]) -> dict[str, float | int]:
    count = len(results)
    if count == 0:
        return {"cases": 0, "pass_rate": 0.0, "answerability_accuracy": 0.0}
    return {
        "cases": count,
        "pass_rate": sum(item.passed for item in results) / count,
        "answerability_accuracy": sum(
            item.answerability_correct for item in results
        )
        / count,
        "mean_source_recall": sum(item.source_recall for item in results) / count,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="技術文書RAGの評価セットを実行")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("sample_data/evaluation.json"),
    )
    parser.add_argument(
        "--ingest-dir",
        type=Path,
        help="評価前に、このフォルダ直下のPDFを登録します。",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    service, _ = build_service(Path.cwd())
    if args.ingest_dir:
        for pdf_path in sorted(args.ingest_dir.glob("*.pdf")):
            service.ingest_pdf(pdf_path.name, pdf_path.read_bytes())
    results = evaluate(service, load_dataset(args.dataset))
    report = {
        "summary": summarize(results),
        "results": [asdict(item) for item in results],
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
