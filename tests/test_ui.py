from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import streamlit as st
from streamlit.testing.v1 import AppTest
from panel_rag.models import DocumentRecord,RAGAnswer


class DemoService:
    def list_documents(self):
        return [DocumentRecord('demo','hash','self-authored.pdf',1,1,'2026-09-07')]
    def ask(self,question):
        return RAGAnswer('登録資料からは確認できない',False,[],[],'extractive','対象の仕様がありません。')


def test_ui_refusal_persists_across_rerun():
    st.cache_resource.clear()
    settings=SimpleNamespace(llm_provider='extractive',embedding_model='offline-test',top_k=5,min_relevance_score=.72)
    with patch('panel_rag.bootstrap.build_service',return_value=(DemoService(),settings)):
        # Keep assertions independent of import/instrumentation speed.
        at=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'streamlit_app.py'),default_timeout=15).run()
        assert not at.exception
        at.text_area[0].set_value('未登録型式の仕様は？')
        at.button[0].click().run()
        assert not at.exception
        assert any('登録資料からは確認できない' in w.value for w in at.warning)
        at.run()
        assert any('登録資料からは確認できない' in w.value for w in at.warning)
    st.cache_resource.clear()


def test_ui_shows_approved_value_and_conditions_not_other_extracted_cells():
    from panel_rag.models import SearchHit,AnswerContext
    class AnswerService(DemoService):
        def ask(self,question):
            h=SearchHit('h','demo','self-authored.pdf',1,'ZX4-24 current 2A',.95,
                        metadata={'structured_facts':[dict(model='ZX4-24',property='output_current',original_label='Rated current',
                                                         value='2A',conditions=['Refer to Derating Curve'])],
                                  'table_facts':[dict(model='ZX4-24',property='Unrequested rating',value='99A')]})
            return RAGAnswer('ZX4-24: 2A / Refer to Derating Curve',True,[AnswerContext('S1',h)],[h],'extractive')
        def document_path(self,document_id):return None
    settings=SimpleNamespace(llm_provider='extractive',embedding_model='offline-test',top_k=5,min_relevance_score=.72)
    st.cache_resource.clear()
    with patch('panel_rag.bootstrap.build_service',return_value=(AnswerService(),settings)):
        at=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'streamlit_app.py'),default_timeout=15).run()
        at.text_area[0].set_value('ZX4-24の定格出力電流は？')
        at.button[0].click().run()
        assert not at.exception
        assert any('2A / Refer to Derating Curve' in t.value for t in at.text)
        tables=[df.value for df in at.dataframe if '値（原文）' in df.value]
        assert len(tables)==1 and tables[0]['値（原文）'].tolist()==['2A']
    st.cache_resource.clear()


def test_ui_corrupt_upload_error_survives_registration_rerun():
    class RejectingService(DemoService):
        def ingest_pdf(self,name,data):
            raise ValueError('PDFを読み取れません。')
    upload=SimpleNamespace(name='broken.pdf',getvalue=lambda:b'not a PDF')
    settings=SimpleNamespace(llm_provider='extractive',embedding_model='offline-test',top_k=5,min_relevance_score=.72)
    st.cache_resource.clear()
    with patch('panel_rag.bootstrap.build_service',return_value=(RejectingService(),settings)), \
         patch('streamlit.file_uploader',return_value=[upload]):
        at=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'streamlit_app.py'),default_timeout=15).run()
        next(b for b in at.button if b.label=='選択した資料を登録').click().run()
        assert not at.exception
        assert any('broken.pdf: PDFを読み取れません。' in e.value for e in at.error)
        at.run()
        assert any('broken.pdf: PDFを読み取れません。' in e.value for e in at.error)
    st.cache_resource.clear()
