import json

from panel_rag.llm import ExtractiveAnswerProvider, OpenAIAnswerProvider
from panel_rag.models import AnswerContext, SearchHit


class FakeResponses:
    def __init__(self) -> None:
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        payload = {
            "supported": True,
            "answer": "定格出力は10Aです。",
            "citation_ids": ["S1"],
        }
        return type("Response", (), {"output_text": json.dumps(payload)})()


class FakeClient:
    def __init__(self) -> None:
        self.responses = FakeResponses()


def test_openai_provider_requests_strict_structured_output() -> None:
    client = FakeClient()
    provider = OpenAIAnswerProvider("test-model", client=client)
    context = AnswerContext(
        "S1", SearchHit("c1", "d1", "spec.pdf", 2, "DC24V 10A", 0.9)
    )

    result = provider.generate("定格出力は？", [context])

    assert result.supported
    assert result.citation_ids == ["S1"]
    assert client.responses.kwargs["store"] is False
    assert client.responses.kwargs["text"]["format"]["strict"] is True


def test_extractive_provider_uses_multiple_hits_only_when_question_requests_it() -> None:
    provider = ExtractiveAnswerProvider()
    contexts = [
        AnswerContext(
            f"S{index}",
            SearchHit(f"c{index}", f"d{index}", f"{index}.pdf", 1, text, 0.9),
        )
        for index, text in enumerate(["DC24V 10A", "DC12-24V sensor"], start=1)
    ]

    single = provider.generate("DC24Vの定格は？", contexts)
    multiple = provider.generate("盤とセンサの電圧を併記して", contexts)

    assert single.citation_ids == ["S1"]
    assert multiple.citation_ids == ["S1", "S2"]
