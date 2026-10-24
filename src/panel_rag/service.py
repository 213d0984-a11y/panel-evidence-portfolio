from __future__ import annotations

import hashlib
import re
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from .chunking import chunk_pages
from .embeddings import Embedder
from .llm import AnswerProvider
from .models import (
    AnswerContext,
    DocumentRecord,
    IngestResult,
    RAGAnswer,
    SearchHit,
)
from .pdf_loader import extract_pdf_pages
from .registry import DocumentRegistry
from .vector_store import QdrantVectorStore
from .lexical import identifiers, identifier_present, linked_identifier_present
from .catalog_tables import CatalogEvidence
from .evidence import check_evidence

REFUSAL_MESSAGE = "登録資料からは確認できない"
_MODEL_NUMBER_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])(?=[A-Za-z0-9._/-]{3,})(?=[A-Za-z0-9._/-]*[A-Za-z])"
    r"(?=[A-Za-z0-9._/-]*\d)[A-Za-z0-9][A-Za-z0-9._/-]*",
    re.IGNORECASE,
)
_JAPANESE_RUN_PATTERN = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]{2,}")
_WORD_PATTERN = re.compile(r"[A-Za-z]{3,}")
_COMMON_JAPANESE_BIGRAMS = {
    "この",
    "その",
    "どの",
    "とは",
    "です",
    "ます",
    "して",
    "えて",
    "くだ",
    "さい",
    "もの",
    "こと",
    "つい",
    "いて",
    "のは",
    "何番",
}
_COMMON_ENGLISH_WORDS = {
    "the",
    "and",
    "for",
    "what",
    "which",
    "please",
    "tell",
    "this",
    "that",
}


class RAGService:
    def __init__(
        self,
        *,
        embedder: Embedder,
        vector_store: QdrantVectorStore,
        registry: DocumentRegistry,
        answer_provider: AnswerProvider,
        uploads_dir: Path,
        min_relevance_score: float = 0.72,
        top_k: int = 5,
        chunk_size: int = 900,
        chunk_overlap: int = 150,
    ) -> None:
        self.embedder = embedder
        self.vector_store = vector_store
        self.registry = registry
        self.answer_provider = answer_provider
        self.uploads_dir = uploads_dir
        self.min_relevance_score = min_relevance_score
        self.top_k = top_k
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.catalog_evidence=CatalogEvidence(self.document_path)

    def ingest_pdf(self, file_name: str, pdf_bytes: bytes) -> IngestResult:
        safe_name = Path(file_name).name
        if not safe_name.lower().endswith(".pdf"):
            raise ValueError("PDFファイルだけ登録できます。")

        digest = hashlib.sha256(pdf_bytes).hexdigest()
        existing = self.registry.find_by_sha256(digest)
        if existing:
            return IngestResult(record=existing, already_registered=True)

        document_id = digest[:20]
        pages = extract_pdf_pages(pdf_bytes, safe_name)
        chunks = chunk_pages(
            pages,
            document_id=document_id,
            file_name=safe_name,
            max_chars=self.chunk_size,
            overlap_chars=self.chunk_overlap,
        )
        vectors = self.embedder.embed_documents([chunk.text for chunk in chunks])
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        upload_path = self.uploads_dir / f"{document_id}.pdf"
        record = DocumentRecord(
            document_id=document_id,
            sha256=digest,
            file_name=safe_name,
            page_count=max(page.page_number for page in pages),
            chunk_count=len(chunks),
            ingested_at_utc=datetime.now(timezone.utc).isoformat(),
        )
        existed=upload_path.exists()
        try:
            upload_path.write_bytes(pdf_bytes)
            self.vector_store.delete_document(document_id)
            self.vector_store.upsert(chunks, vectors)
            self.registry.add(record)
        except Exception:
            # Failed registration must not leave searchable orphan chunks.
            # Keep any pre-existing original; remove only this new upload.
            self.vector_store.delete_document(document_id)
            if not existed and upload_path.exists(): upload_path.unlink()
            raise
        return IngestResult(record=record)

    def ask(self, question: str) -> RAGAnswer:
        self.last_evidence_check = None
        self.last_citation_check = None
        question = question.strip()
        if not question:
            raise ValueError("質問を入力してください。")

        query_vector = self.embedder.embed_query(question)
        if hasattr(self.vector_store, 'search_evidence'):
            retrieved = self.vector_store.search_evidence(query_vector, limit=self.top_k,
                question=question, min_score=self.min_relevance_score,
                page_enricher=self.catalog_evidence.enrich_pages)
        else:
            retrieved = self.vector_store.search(query_vector, limit=self.top_k, question=question)
        proof_pages={(h.document_id,n) for h in retrieved if h.score>=self.min_relevance_score
                     for n in h.metadata.get('required_source_pages',[])}
        eligible = [hit for hit in retrieved if hit.score >= self.min_relevance_score
                    or (hit.metadata.get('binding_proof_only') and (hit.document_id,hit.page_number) in proof_pages)]

        if not eligible:
            return self._refuse(retrieved, "検索スコアが基準未満です。")
        if not _model_number_anchors_are_present(question, eligible):
            return self._refuse(retrieved, "質問中の型式が根拠内にありません。")
        evidence_check = check_evidence(question, eligible)
        self.last_evidence_check = evidence_check
        if not evidence_check.supported:
            reason = evidence_check.reason if evidence_check.requirements else "質問の主題語が根拠内にありません。"
            return self._refuse(retrieved, reason)

        # Retain only pages contributing to the complete subject/property set.
        contributions = {}
        approved_facts = {}
        for item in evidence_check.details:
            if not item['missing_qualifiers']:
                key = (item['document_id'], item['page'])
                contributions.setdefault(key, set()).update((item['model'], prop) for prop in item['found'])
                approved_facts.setdefault(key,[]).extend(item.get('matched_facts',[]))
        supported_pages, covered = set(), set()
        for hit in eligible:
            key = (hit.document_id, hit.page_number)
            gain = contributions.get(key, set()) - covered
            if gain:
                supported_pages.add(key)
                covered.update(gain)
        for hit in eligible:
            if (hit.document_id,hit.page_number) in supported_pages:
                supported_pages.update((hit.document_id,n) for n in hit.metadata.get('required_source_pages',[]))
        generation_hits = [hit for hit in eligible
                           if (hit.document_id, hit.page_number) in supported_pages]
        # Enrich citations, not the answerability decision, with exact grid
        # cells. Failure to parse a table never authorizes an answer.
        enriched=[]
        for hit in generation_hits:
            path=self.document_path(hit.document_id)
            facts=[]
            if path is not None:
                from .tables import extract_table_facts
                try:
                    facts=extract_table_facts(path,hit.page_number,question)
                except Exception:
                    pass  # original page text remains available for inspection
            enriched.append(replace(hit,metadata={**hit.metadata,'table_facts':facts,
                'structured_facts':[f for f in hit.metadata.get('structured_facts',[])
                                    if f in approved_facts.get((hit.document_id,hit.page_number),[])]}))
        generation_hits=enriched
        if not generation_hits:
            return self._refuse(retrieved, "回答へ渡せる十分な仕様根拠がありません。")
        contexts = [
            AnswerContext(context_id=f"S{index}", hit=hit)
            for index, hit in enumerate(generation_hits, start=1)
        ]
        generated = self.answer_provider.generate(question, contexts)
        context_by_id = {context.context_id: context for context in contexts}

        if not generated.supported or not generated.answer.strip():
            return self._refuse(retrieved, "回答生成側が根拠不足と判定しました。")
        if not generated.citation_ids:
            return self._refuse(retrieved, "回答に引用がありません。")
        if any(item not in context_by_id for item in generated.citation_ids):
            return self._refuse(retrieved, "回答に不正な引用IDがあります。")

        unique_ids = list(dict.fromkeys(generated.citation_ids))
        cited_pages = {(context_by_id[item].hit.document_id, context_by_id[item].hit.page_number) for item in unique_ids}
        citation_check = check_evidence(question, eligible, cited_pages)
        self.last_citation_check = citation_check
        if not citation_check.supported:
            return self._refuse(retrieved, "引用されたページに要求仕様の根拠が不足しています。")
        return RAGAnswer(
            answer=generated.answer.strip(),
            answerable=True,
            citations=[context_by_id[item] for item in unique_ids],
            retrieved_hits=retrieved,
            provider_name=self.answer_provider.name,
        )

    def list_documents(self) -> list[DocumentRecord]:
        return self.registry.list_documents()

    def document_path(self, document_id: str) -> Path | None:
        """Return only a registered PDF, never a user-supplied filesystem path."""
        if not re.fullmatch(r'[0-9a-f]{20}',document_id): return None
        if not any(d.document_id==document_id for d in self.list_documents()): return None
        path=self.uploads_dir / f'{document_id}.pdf'
        return path if path.is_file() else None

    def _refuse(self, retrieved: list[SearchHit], reason: str) -> RAGAnswer:
        return RAGAnswer(
            answer=REFUSAL_MESSAGE,
            answerable=False,
            citations=[],
            retrieved_hits=retrieved,
            provider_name=self.answer_provider.name,
            refusal_reason=reason,
        )


def _model_number_anchors_are_present(
    question: str, eligible_hits: list[SearchHit]
) -> bool:
    anchors = identifiers(question)
    if not anchors:
        return True
    evidence = "\n".join(hit.text for hit in eligible_hits).lower()
    return all(any(linked_identifier_present(anchor, hit) for hit in eligible_hits) for anchor in anchors)


def _topic_anchors_are_present(
    question: str, eligible_hits: list[SearchHit]
) -> bool:
    """意味的に近いだけの誤検索を、軽量な本文一致で追加抑制する。"""
    without_models = _MODEL_NUMBER_PATTERN.sub(" ", question)
    japanese_bigrams: set[str] = set()
    for run in _JAPANESE_RUN_PATTERN.findall(without_models):
        japanese_bigrams.update(
            run[index : index + 2] for index in range(len(run) - 1)
        )
    japanese_bigrams -= _COMMON_JAPANESE_BIGRAMS

    english_words = {
        item.lower() for item in _WORD_PATTERN.findall(without_models)
    } - _COMMON_ENGLISH_WORDS
    anchors = japanese_bigrams | english_words
    if not anchors:
        return True

    evidence = "\n".join(hit.text for hit in eligible_hits).lower()
    return any(anchor.lower() in evidence for anchor in anchors)
