from panel_rag.evaluation import evaluate, summarize
from panel_rag.models import (
    AnswerContext,
    RAGAnswer,
    SearchHit,
)


class FakeService:
    def ask(self, question: str) -> RAGAnswer:
        if question == "known":
            hit = SearchHit("c1", "d1", "spec.pdf", 1, "DC24V 10A", 0.9)
            context = AnswerContext("S1", hit)
            return RAGAnswer("DC24V 10A", True, [context], [hit], "fake")
        return RAGAnswer(
            "登録資料からは確認できない", False, [], [], "fake", "low score"
        )


def test_evaluation_reports_answerability_and_source_recall() -> None:
    cases = [
        {
            "id": "1",
            "question": "known",
            "expected_answerable": True,
            "expected_sources": ["spec.pdf"],
            "expected_terms": ["10A"],
            "categories": ["answerable", "numeric"],
        },
        {
            "id": "2",
            "question": "unknown",
            "expected_answerable": False,
            "expected_sources": [],
            "expected_terms": [],
            "categories": ["unanswerable"],
        },
    ]

    results = evaluate(FakeService(), cases)
    summary = summarize(results)

    assert all(item.passed for item in results)
    assert summary["pass_rate"] == 1.0
    assert summary["answerability_accuracy"] == 1.0

