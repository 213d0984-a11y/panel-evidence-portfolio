from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class AppSettings:
    data_dir: Path
    embedding_model: str = "intfloat/multilingual-e5-small"
    min_relevance_score: float = 0.72
    top_k: int = 5
    chunk_size: int = 900
    chunk_overlap: int = 150
    llm_provider: str = "extractive"
    llm_model: str = "gpt-5.4-mini"

    @classmethod
    def from_env(cls, base_dir: Path | None = None) -> "AppSettings":
        load_dotenv()
        base = (base_dir or Path.cwd()).resolve()
        raw_data_dir = Path(os.getenv("RAG_DATA_DIR", "data"))
        data_dir = raw_data_dir if raw_data_dir.is_absolute() else base / raw_data_dir

        settings = cls(
            data_dir=data_dir.resolve(),
            embedding_model=os.getenv(
                "RAG_EMBEDDING_MODEL", "intfloat/multilingual-e5-small"
            ).strip(),
            min_relevance_score=float(
                os.getenv("RAG_MIN_RELEVANCE_SCORE", "0.72")
            ),
            top_k=int(os.getenv("RAG_TOP_K", "5")),
            chunk_size=int(os.getenv("RAG_CHUNK_SIZE", "900")),
            chunk_overlap=int(os.getenv("RAG_CHUNK_OVERLAP", "150")),
            llm_provider=os.getenv("RAG_LLM_PROVIDER", "extractive").strip().lower(),
            llm_model=os.getenv("RAG_LLM_MODEL", "gpt-5.4-mini").strip(),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if not 0 <= self.min_relevance_score <= 1:
            raise ValueError("RAG_MIN_RELEVANCE_SCORE は0〜1で指定してください。")
        if self.top_k < 1:
            raise ValueError("RAG_TOP_K は1以上で指定してください。")
        if self.chunk_size < 100:
            raise ValueError("RAG_CHUNK_SIZE は100以上で指定してください。")
        if not 0 <= self.chunk_overlap < self.chunk_size:
            raise ValueError("RAG_CHUNK_OVERLAP は0以上かつCHUNK_SIZE未満です。")
        if self.llm_provider not in {"extractive", "openai"}:
            raise ValueError("RAG_LLM_PROVIDER は extractive または openai です。")

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def qdrant_dir(self) -> Path:
        return self.data_dir / "qdrant"

    @property
    def registry_path(self) -> Path:
        return self.data_dir / "documents.json"

