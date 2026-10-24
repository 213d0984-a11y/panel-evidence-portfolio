import importlib.util
from pathlib import Path
from panel_rag.models import RAGAnswer,SearchHit,AnswerContext

spec=importlib.util.spec_from_file_location('public_benchmark',Path(__file__).resolve().parents[1]/'scripts/evaluate_benchmark.py')
benchmark=importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)

def test_page_metrics_distinguish_retrieval_from_citation():
    case=dict(question_id='example',category='test',expected_answerable=True,
              expected_document=['a.pdf','b.pdf'],expected_page={'a.pdf':[2],'b.pdf':[3]})
    a=SearchHit('a','a','a.pdf',2,'example',.9)
    b=SearchHit('b','b','b.pdf',1,'example',.9)
    row=benchmark.grade(case,RAGAnswer('text',True,[AnswerContext('S1',a)],[a,b],'extractive'))
    assert row['document_retrieval_recall']==1
    assert row['page_retrieval_recall']==.5
    assert row['citation_recall']==.5
    assert not row['strict_pass']

def test_negative_and_positive_denominators_remain_separate():
    positive={'question_id':'positive','category':'test','expected_answerable':True,
              'expected_document':['a.pdf'],'expected_page':{'a.pdf':[1]}}
    negative={**positive,'question_id':'negative','expected_answerable':False,
              'expected_document':[],'expected_page':{}}
    refusal=RAGAnswer('not confirmed',False,[],[],'extractive')
    rows=[benchmark.grade(c,refusal) for c in [positive,negative]]
    summary=benchmark.summarize(rows)
    assert summary['answerability_accuracy']==.5
    assert summary['answerable_false_refusal_rate']==1
    assert summary['unanswerable_refusal_rate']==1
    assert summary['document_retrieval_recall']==0


def test_whole_page_with_correct_numbers_does_not_count_as_direct_answer():
    from panel_rag.evidence import EvidenceCheck
    h=SearchHit('a','a','a.pdf',1,'ZX-24 2A ZX-48 1A',.95)
    check=EvidenceCheck(True,'ok',details=[{'model':'zx-24','found':['output_current']}])
    answer=RAGAnswer(h.text,True,[AnswerContext('S1',h)],[h],'extractive')
    row=benchmark.presentation(answer,check)
    assert row['answer_presentation']=='page_excerpt_or_mixed'
    assert not row['complete_bound_value_presentation']


def test_partial_comparison_cannot_count_as_complete_bound_presentation():
    from panel_rag.evidence import EvidenceCheck
    h=SearchHit('a','a','a.pdf',1,'ZX-24 ZX-48',.95,
                metadata={'structured_facts':[dict(model='ZX-24',property='output_current',value='2A')]})
    check=EvidenceCheck(True,'ok',details=[{'model':model,'found':['output_current']} for model in ['zx-24','zx-48']])
    answer=RAGAnswer('typed values',True,[AnswerContext('S1',h)],[h],'extractive')
    assert not benchmark.presentation(answer,check)['complete_bound_value_presentation']
    h.metadata['structured_facts'].append(dict(model='ZX-48',property='output_current',value='1A'))
    assert benchmark.presentation(answer,check)['complete_bound_value_presentation']
