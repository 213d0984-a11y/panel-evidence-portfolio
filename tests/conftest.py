from __future__ import annotations

import math
from collections.abc import Sequence

import pytest

from panel_rag.models import AnswerContext, GeneratedAnswer


class KeywordEmbedder:
    name = "test-keyword-embedder"
    dimension = 4

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    def _vector(self, text: str) -> list[float]:
        lowered = text.lower()
        values = [
            float("24v" in lowered or "pwr-240-24" in lowered),
            float("温度" in text or "temperature" in lowered),
            float("絶縁" in text or "inspection" in lowered),
            float(
                not any(
                    term in lowered
                    for term in ("24v", "pwr-240-24", "temperature", "inspection")
                )
                and "温度" not in text
                and "絶縁" not in text
            ),
        ]
        norm = math.sqrt(sum(item * item for item in values)) or 1.0
        return [item / norm for item in values]


class StubProvider:
    name = "stub"

    def __init__(
        self,
        *,
        supported: bool = True,
        citation_ids: list[str] | None = None,
    ) -> None:
        self.supported = supported
        self.citation_ids = citation_ids
        self.calls = 0

    def generate(
        self, question: str, contexts: Sequence[AnswerContext]
    ) -> GeneratedAnswer:
        del question
        self.calls += 1
        citations = self.citation_ids
        if citations is None:
            citations = [contexts[0].context_id] if contexts else []
        return GeneratedAnswer(
            supported=self.supported,
            answer="DC24V 10Aです。" if self.supported else "",
            citation_ids=citations,
        )


@pytest.fixture
def keyword_embedder() -> KeywordEmbedder:
    return KeywordEmbedder()

