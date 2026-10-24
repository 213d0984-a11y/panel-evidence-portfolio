from __future__ import annotations

from typing import Protocol, Sequence


class Embedder(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def dimension(self) -> int: ...

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class SentenceTransformerEmbedder:
    """SentenceTransformersを薄く包み、交換点を明示する。"""

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._model = None

    @property
    def name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        model = self._load_model()
        if hasattr(model, "get_embedding_dimension"):
            return int(model.get_embedding_dimension())
        return int(model.get_sentence_embedding_dimension())

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        prepared = [self._prepare(text, is_query=False) for text in texts]
        vectors = self._load_model().encode(
            prepared,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return vectors.tolist()

    def embed_query(self, text: str) -> list[float]:
        vector = self._load_model().encode(
            self._prepare(text, is_query=True),
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return vector.tolist()

    def _load_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name)
        return self._model

    def _prepare(self, text: str, *, is_query: bool) -> str:
        if "e5" not in self._model_name.lower():
            return text
        prefix = "query: " if is_query else "passage: "
        return prefix + text
