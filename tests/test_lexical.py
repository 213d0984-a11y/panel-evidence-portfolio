import pytest
from panel_rag.lexical import identifiers, identifier_present, normalize, metadata
from panel_rag.models import TextChunk
from panel_rag.vector_store import QdrantVectorStore

@pytest.mark.parametrize('value', ['S8VK-G06024','s8vk g06024','Ｓ８ＶＫ－Ｇ０６０２４','S8VK–G 06024'])
def test_model_variants(value):
    assert identifiers(value) == ['s8vk-g06024']
    assert identifier_present('S8VK-G06024', value)

def test_units_and_similar_models():
    assert normalize('60 W') == normalize('60W')
    assert not identifier_present('S8VK-G06024', 'S8VK-G060240 S8VK-G12024')
    assert not identifier_present('ZX-900', 'ZX-901')
    assert identifier_present('FR-D820', 'FR-D820-0.75K-042')
    assert normalize('power 60 W') == 'power 60w'
    assert not identifier_present('ZX-9.1', 'ZX-9.2')

def test_metadata_does_not_guess():
    result = metadata('ZX9 Series specifications', 'unknown.pdf')
    assert result['manufacturer'] is None
    assert result['category'] is None
    assert result['series'] == ['ZX9']

def test_compact_identifier_without_shared_bm25_token():
    store = QdrantVectorStore(':memory:', vector_size=2)
    try:
        store.upsert([TextChunk('a','a','a.pdf',1,0,'other text'),
                      TextChunk('b','b','b.pdf',1,0,'ZX-901')],[[1,0],[0.8,0.6]])
        assert store.search([1,0],limit=1,question='ZX901')[0].file_name == 'b.pdf'
    finally: store.close()

def test_hybrid_prefers_identifier_and_preserves_cosine():
    store = QdrantVectorStore(':memory:', vector_size=2)
    try:
        store.upsert([TextChunk('a','a','unrelated.pdf',1,0,'Motor output voltage'),
                      TextChunk('b','b','target.pdf',2,0,'ZX-901 output 60 W')], [[1,0],[0.8,0.6]])
        hits = store.search([1,0],limit=2,question='ZX 901 output 60W')
        assert hits[0].file_name == 'target.pdf'
        assert hits[0].score == pytest.approx(0.8)
        assert hits[0].fusion_score is not None
        store.delete_document('b')
        assert store.search([1,0],limit=2,question='ZX-901')[0].file_name == 'unrelated.pdf'
    finally:
        store.close()
