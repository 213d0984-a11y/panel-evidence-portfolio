from __future__ import annotations

import uuid
from pathlib import Path
from typing import Sequence

from qdrant_client import QdrantClient, models

from .models import SearchHit, TextChunk
from .lexical import LexicalIndex, metadata
from dataclasses import replace


class QdrantVectorStore:
    def __init__(
        self,
        path: Path | str,
        *,
        vector_size: int,
        collection_name: str = "technical_documents",
    ) -> None:
        self.path = path
        self.vector_size = vector_size
        self.collection_name = collection_name
        if str(path) == ":memory:":
            self.client = QdrantClient(location=":memory:")
        else:
            Path(path).mkdir(parents=True, exist_ok=True)
            self.client = QdrantClient(path=str(path))
        self._ensure_collection()
        self._lexical = None

    def upsert(self, chunks: Sequence[TextChunk], vectors: Sequence[list[float]]) -> None:
        self._lexical = None
        if len(chunks) != len(vectors):
            raise ValueError("チャンク数とベクトル数が一致しません。")
        points = [
            models.PointStruct(
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, chunk.chunk_id)),
                vector=vector,
                payload={
                    "chunk_id": chunk.chunk_id,
                    "document_id": chunk.document_id,
                    "file_name": chunk.file_name,
                    "page_number": chunk.page_number,
                    "text": chunk.text,
                    "search_metadata": metadata(chunk.text, chunk.file_name),
                },
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        if points:
            self.client.upsert(
                collection_name=self.collection_name,
                points=points,
                wait=True,
            )

    def search(self, query_vector: list[float], *, limit: int, question: str | None = None) -> list[SearchHit]:
        response = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            limit=max(1, self.count()) if question else limit,
            with_payload=True,
        )
        hits: list[SearchHit] = []
        for point in response.points:
            payload = point.payload or {}
            hits.append(
                SearchHit(
                    chunk_id=str(payload["chunk_id"]),
                    document_id=str(payload["document_id"]),
                    file_name=str(payload["file_name"]),
                    page_number=int(payload["page_number"]),
                    text=str(payload["text"]),
                    score=float(point.score),
                    metadata=payload.get('search_metadata') or metadata(str(payload['text']), str(payload['file_name'])),
                )
            )
        if not question or not hits:
            return hits[:limit]
        # Full scan is deliberate for the small local corpus: no new vector schema,
        # no embeddings rebuilt. Cache only the lexical token statistics.
        if self._lexical is None:
            self._lexical = LexicalIndex(sorted(hits, key=lambda h: h.chunk_id))
        lexical = self._lexical.search(question)
        dense_rank = {h.chunk_id: rank for rank, h in enumerate(hits, 1)}
        dense_hits = {h.chunk_id: h for h in hits}
        fusion = {h.chunk_id: (0, 1/(60+dense_rank[h.chunk_id]), 0.0) for h in hits}
        for rank, (index, matches, bm25) in enumerate(lexical, 1):
            key = self._lexical.hits[index].chunk_id
            fusion[key] = (matches, fusion[key][1] + 1/(60+rank), bm25)
        ordered = sorted(fusion, key=lambda key: (-fusion[key][0], -fusion[key][1], key))
        # score remains cosine similarity: the existing threshold must not be
        # applied to a numerically unrelated RRF score.
        return [replace(dense_hits[key], fusion_score=fusion[key][1], lexical_score=fusion[key][2])
                for key in ordered[:limit]]

    def search_evidence(self, query_vector, *, limit, question, min_score, page_enricher=None):
        from .retrieval import evidence_pages
        candidates = self.search(query_vector, limit=max(1, self.count()), question=question)
        return evidence_pages(question, candidates, limit, min_score, page_enricher)

    def delete_document(self, document_id: str) -> None:
        self._lexical = None
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="document_id",
                            match=models.MatchValue(value=document_id),
                        )
                    ]
                )
            ),
            wait=True,
        )

    def count(self) -> int:
        return int(
            self.client.count(
                collection_name=self.collection_name, exact=True
            ).count
        )

    def close(self) -> None:
        self.client.close()

    def _ensure_collection(self) -> None:
        if not self.client.collection_exists(self.collection_name):
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(
                    size=self.vector_size,
                    distance=models.Distance.COSINE,
                ),
            )
            return

        collection = self.client.get_collection(self.collection_name)
        vectors = collection.config.params.vectors
        existing_size = getattr(vectors, "size", None)
        if existing_size is not None and int(existing_size) != self.vector_size:
            raise RuntimeError(
                "既存インデックスとEmbeddingの次元数が異なります。"
                "RAG_DATA_DIRを分けるか、dataを退避して再登録してください。"
            )
