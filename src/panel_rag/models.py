from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PageText:
    page_number: int
    text: str


@dataclass(frozen=True)
class TextChunk:
    chunk_id: str
    document_id: str
    file_name: str
    page_number: int
    chunk_index: int
    text: str


@dataclass(frozen=True)
class SearchHit:
    chunk_id: str
    document_id: str
    file_name: str
    page_number: int
    text: str
    score: float
    fusion_score: float | None = None
    lexical_score: float | None = None
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class AnswerContext:
    context_id: str
    hit: SearchHit


@dataclass(frozen=True)
class GeneratedAnswer:
    supported: bool
    answer: str
    citation_ids: list[str]


@dataclass(frozen=True)
class RAGAnswer:
    answer: str
    answerable: bool
    citations: list[AnswerContext]
    retrieved_hits: list[SearchHit]
    provider_name: str
    refusal_reason: str | None = None


@dataclass(frozen=True)
class DocumentRecord:
    document_id: str
    sha256: str
    file_name: str
    page_count: int
    chunk_count: int
    ingested_at_utc: str


@dataclass(frozen=True)
class IngestResult:
    record: DocumentRecord
    already_registered: bool = False


@dataclass
class EvaluationResult:
    case_id: str
    question: str
    categories: list[str]
    expected_answerable: bool
    actual_answerable: bool
    answerability_correct: bool
    source_recall: float
    term_coverage: float | None
    passed: bool
    answer: str
    retrieved_sources: list[str] = field(default_factory=list)
