from datetime import datetime, timezone

from panel_rag.models import DocumentRecord
from panel_rag.registry import DocumentRegistry


def test_registry_round_trip(tmp_path) -> None:
    registry = DocumentRegistry(tmp_path / "documents.json")
    record = DocumentRecord(
        document_id="doc-1",
        sha256="abc",
        file_name="spec.pdf",
        page_count=2,
        chunk_count=4,
        ingested_at_utc=datetime.now(timezone.utc).isoformat(),
    )

    registry.add(record)

    assert registry.list_documents() == [record]
    assert registry.find_by_sha256("abc") == record

