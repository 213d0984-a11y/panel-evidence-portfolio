import pymupdf
import pytest
from panel_rag.service import RAGService
from panel_rag.vector_store import QdrantVectorStore
from panel_rag.registry import DocumentRegistry
from conftest import StubProvider


def pdf_bytes():
    with pymupdf.open() as pdf:
        pdf.new_page().insert_text((72,72),'DC24V Output 10A')
        return pdf.tobytes()


@pytest.mark.parametrize('failure',['registry','after_index'])
def test_failed_ingest_does_not_leave_searchable_orphans(tmp_path,keyword_embedder,monkeypatch,failure):
    store=QdrantVectorStore(':memory:',vector_size=4)
    registry=DocumentRegistry(tmp_path/'documents.json')
    service=RAGService(embedder=keyword_embedder,vector_store=store,registry=registry,
                       answer_provider=StubProvider(),uploads_dir=tmp_path/'uploads')
    try:
        if failure=='registry':
            def fail(_): raise OSError('disk full')
            monkeypatch.setattr(registry,'add',fail)
        else:
            original=store.upsert
            def fail(chunks,vectors):
                original(chunks,vectors)
                raise OSError('write interrupted')
            monkeypatch.setattr(store,'upsert',fail)
        with pytest.raises(OSError): service.ingest_pdf('self-authored.pdf',pdf_bytes())
        assert store.count()==0
        assert registry.list_documents()==[]
        assert not list((tmp_path/'uploads').glob('*.pdf'))
    finally:
        store.close()
