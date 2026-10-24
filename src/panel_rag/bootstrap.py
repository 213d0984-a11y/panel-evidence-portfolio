from __future__ import annotations

from pathlib import Path

from .config import AppSettings
from .embeddings import SentenceTransformerEmbedder
from .llm import ExtractiveAnswerProvider, OpenAIAnswerProvider
from .registry import DocumentRegistry
from .service import RAGService
from .vector_store import QdrantVectorStore


def build_service(base_dir: Path | None = None) -> tuple[RAGService, AppSettings]:
    settings = AppSettings.from_env(base_dir)
    embedder = SentenceTransformerEmbedder(settings.embedding_model)
    vector_store = QdrantVectorStore(
        settings.qdrant_dir,
        vector_size=embedder.dimension,
    )
    registry = DocumentRegistry(settings.registry_path)
    if settings.llm_provider == "openai":
        provider = OpenAIAnswerProvider(settings.llm_model)
    else:
        provider = ExtractiveAnswerProvider()

    service = RAGService(
        embedder=embedder,
        vector_store=vector_store,
        registry=registry,
        answer_provider=provider,
        uploads_dir=settings.uploads_dir,
        min_relevance_score=settings.min_relevance_score,
        top_k=settings.top_k,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )
    return service, settings

