from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from threading import Lock

from .models import DocumentRecord


class DocumentRegistry:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = Lock()

    def list_documents(self) -> list[DocumentRecord]:
        payload = self._read()
        records = [DocumentRecord(**item) for item in payload["documents"]]
        return sorted(records, key=lambda item: item.ingested_at_utc, reverse=True)

    def find_by_sha256(self, sha256: str) -> DocumentRecord | None:
        return next(
            (item for item in self.list_documents() if item.sha256 == sha256),
            None,
        )

    def add(self, record: DocumentRecord) -> None:
        with self._lock:
            payload = self._read()
            payload["documents"] = [
                item
                for item in payload["documents"]
                if item["document_id"] != record.document_id
            ]
            payload["documents"].append(asdict(record))
            self._write(payload)

    def _read(self) -> dict:
        if not self.path.exists():
            return {"version": 1, "documents": []}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("文書台帳を読み取れません。") from exc
        if payload.get("version") != 1 or not isinstance(payload.get("documents"), list):
            raise RuntimeError("文書台帳の形式が不正です。")
        return payload

    def _write(self, payload: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(temporary, self.path)

