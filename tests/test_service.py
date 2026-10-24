from __future__ import annotations

import pymupdf

from panel_rag.models import DocumentRecord, TextChunk
from panel_rag.registry import DocumentRegistry
from panel_rag.service import REFUSAL_MESSAGE, RAGService
from panel_rag.vector_store import QdrantVectorStore

from conftest import StubProvider


def make_pdf(text: str) -> bytes:
    document = pymupdf.open()
    try:
        page = document.new_page()
        page.insert_text((72, 72), text)
        return document.tobytes()
    finally:
        document.close()


def build_test_service(tmp_path, keyword_embedder, provider: StubProvider) -> RAGService:
    return RAGService(
        embedder=keyword_embedder,
        vector_store=QdrantVectorStore(":memory:", vector_size=4),
        registry=DocumentRegistry(tmp_path / "documents.json"),
        answer_provider=provider,
        uploads_dir=tmp_path / "uploads",
        min_relevance_score=0.75,
        top_k=3,
        chunk_size=300,
        chunk_overlap=30,
    )


def test_ingest_and_answer_with_source(tmp_path, keyword_embedder) -> None:
    provider = StubProvider()
    service = build_test_service(tmp_path, keyword_embedder, provider)
    ingest = service.ingest_pdf(
        "panel.pdf", make_pdf("DC24V power supply PWR-240-24 output is 10A.")
    )

    result = service.ask("DC24V power supply output?")

    assert not ingest.already_registered
    assert result.answerable
    assert result.citations[0].hit.file_name == "panel.pdf"
    assert result.citations[0].hit.page_number == 1
    assert provider.calls == 1


def test_duplicate_pdf_is_not_indexed_twice(tmp_path, keyword_embedder) -> None:
    provider = StubProvider()
    service = build_test_service(tmp_path, keyword_embedder, provider)
    pdf = make_pdf("DC24V power supply output is 10A.")

    first = service.ingest_pdf("panel.pdf", pdf)
    second = service.ingest_pdf("renamed.pdf", pdf)

    assert not first.already_registered
    assert second.already_registered
    assert len(service.list_documents()) == 1
    assert service.vector_store.count() == 1


def test_low_score_refuses_without_calling_provider(tmp_path, keyword_embedder) -> None:
    provider = StubProvider()
    service = build_test_service(tmp_path, keyword_embedder, provider)
    service.ingest_pdf("panel.pdf", make_pdf("DC24V power supply output is 10A."))

    result = service.ask("hydraulic pressure setting?")

    assert not result.answerable
    assert result.answer == REFUSAL_MESSAGE
    assert provider.calls == 0


def test_missing_model_number_anchor_is_refused(tmp_path, keyword_embedder) -> None:
    provider = StubProvider()
    service = build_test_service(tmp_path, keyword_embedder, provider)
    service.ingest_pdf("panel.pdf", make_pdf("DC24V PWR-240-24 output is 10A."))

    result = service.ask("ZX-900のDC24V出力は？")

    assert not result.answerable
    assert result.refusal_reason == "質問中の型式が根拠内にありません。"
    assert provider.calls == 0


def test_missing_topic_word_is_refused_even_with_high_vector_score(
    tmp_path, keyword_embedder
) -> None:
    provider = StubProvider()
    service = build_test_service(tmp_path, keyword_embedder, provider)
    service.ingest_pdf("panel.pdf", make_pdf("DC24V output is 10A."))

    result = service.ask("DC24V装置の塗装色は？")

    assert not result.answerable
    assert result.refusal_reason == "質問の主題語が根拠内にありません。"
    assert provider.calls == 0


def test_invalid_llm_citation_is_refused(tmp_path, keyword_embedder) -> None:
    provider = StubProvider(citation_ids=["NOT-FOUND"])
    service = build_test_service(tmp_path, keyword_embedder, provider)
    service.ingest_pdf("panel.pdf", make_pdf("DC24V output is 10A."))

    result = service.ask("DC24V output?")

    assert not result.answerable
    assert result.answer == REFUSAL_MESSAGE
    assert "不正な引用ID" in (result.refusal_reason or "")


def test_provider_can_decline_answer(tmp_path, keyword_embedder) -> None:
    provider = StubProvider(supported=False)
    service = build_test_service(tmp_path, keyword_embedder, provider)
    service.ingest_pdf("panel.pdf", make_pdf("DC24V output is 10A."))

    result = service.ask("DC24V output?")

    assert not result.answerable
    assert result.answer == REFUSAL_MESSAGE
