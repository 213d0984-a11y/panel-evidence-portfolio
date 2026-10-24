from panel_rag.models import SearchHit
from panel_rag.service import RAGService
from panel_rag.registry import DocumentRegistry
from conftest import StubProvider


class FixedSearch:
    def __init__(self, hits):
        self.hits = hits

    def search(self, *args, **kwargs):
        return self.hits


def service(tmp_path, keyword_embedder, hits):
    return RAGService(
        embedder=keyword_embedder, vector_store=FixedSearch(hits),
        registry=DocumentRegistry(tmp_path / 'documents.json'),
        answer_provider=StubProvider(), uploads_dir=tmp_path / 'uploads')


def test_high_lexical_and_model_match_do_not_authorize_answer(tmp_path, keyword_embedder):
    hit = SearchHit('1', 'doc', 'manual.pdf', 1,
                    'ZX-100 Output voltage 24 V. Product communications overview.',
                    .99, fusion_score=1.0, lexical_score=1000.0)
    rag = service(tmp_path, keyword_embedder, [hit])
    result = rag.ask('ZX-100の通信速度は？')
    assert not result.answerable
    assert rag.answer_provider.calls == 0


def test_only_supporting_page_reaches_provider_without_changing_retrieval(tmp_path, keyword_embedder):
    hits = [SearchHit('1', 'doc', 'manual.pdf', 1, 'ZX-100 Product outline', .99),
            SearchHit('2', 'doc', 'manual.pdf', 2, 'ZX-100 Output voltage 24 V', .85)]
    rag = service(tmp_path, keyword_embedder, hits)
    result = rag.ask('ZX-100の出力電圧は？')
    assert result.answerable
    assert result.retrieved_hits == hits
    assert result.citations[0].hit.page_number == 2
