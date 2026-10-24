from copy import deepcopy
from dataclasses import replace
from panel_rag.contact_tables import model_profiles,rated_rows,column_ratings,link_ratings
from panel_rag.evidence import check_evidence
from panel_rag.models import SearchHit
from panel_rag.lexical import subjects


def grid(rows):
    return dict(rows=rows,boxes=[[(c*20,r*10,(c+1)*20,(r+1)*10) if v else None
                                 for c,v in enumerate(row)] for r,row in enumerate(rows)])


def profiles():
    table=grid([['Type','Blade Models',None],['Model','AX1S','AX2S'],['No. of poles','1','2']])
    table['boxes'][0][1]=(20,0,60,10)
    return table


def rating_table():
    t=grid([['Group','Poles','Contact','Rated Load',None,None,'Allowable Contact Power'],
            [None,None,None,'Voltage','Resistive Load','Inductive Load','Resistive Load'],
            ['Blade Models','2 poles','NO','250V AC','8A','4A','20A'],
            [None,None,'NC','30V DC','6A','3A','18A']])
    t['boxes'][0][3]=(60,0,120,10)
    for c in [0,1]: t['boxes'][2][c]=(c*20,20,(c+1)*20,40)
    return t


def test_identity_profiles_require_literal_poles_and_construction():
    p=model_profiles(profiles(),1)
    assert {(x['model'],x['poles'],x['category']) for x in p}=={('AX1S','1','Blade Models'),('AX2S','2','Blade Models')}
    t=profiles(); t['rows'][2][0]='Capacity'
    assert model_profiles(t,1)==[]
    t=profiles(); t['boxes'][0][1]=(20,0,40,10)
    assert {x['model'] for x in model_profiles(t,1)}=={'AX1S'}


def test_annotated_duplicate_model_does_not_select_default_option():
    t=profiles();t['rows'].append(['Options','AX1S high capacity',None]);t['boxes'].append([(0,30,20,40),(20,30,40,40),None])
    assert {p['model'] for p in model_profiles(t,1)}=={'AX2S'}


def test_rated_load_excludes_allowable_contact_power_and_keeps_voltage():
    rows=rated_rows(rating_table(),2)
    assert len(rows)==4
    assert {r['value'] for r in rows}=={'8A at 250V AC','4A at 250V AC','6A at 30V DC','3A at 30V DC'}
    assert all(r['category']=='Blade Models' and r['poles']=='2' for r in rows)
    assert {r['contact'] for r in rows}=={'NO','NC'}


def test_missing_group_span_and_unrelated_voltage_fail_closed():
    t=rating_table();t['boxes'][2][0]=(0,20,20,30)
    assert {r['contact'] for r in rated_rows(t,2)}=={'NO'}
    t=rating_table();t['rows'][2][3]='See separate manual'
    assert {r['contact'] for r in rated_rows(t,2)}=={'NC'}


def test_identity_join_requires_unique_model_and_unique_table_page():
    p=model_profiles(profiles(),1);rows=rated_rows(rating_table(),2)
    facts=link_ratings(p,rows)[2]
    assert all(f['model']=='AX2S' and f['binding']['page']==1 for f in facts)
    assert link_ratings(p+p,rows)=={}
    assert link_ratings(p,rows+[{**r,'page':3} for r in rows])=={}
    other=[{**r,'category':'PCB Models'} for r in rows]
    assert link_ratings(p,other)=={}


def nested():
    t=grid([['Item','2 poles',None,'4 poles'],
            [None,'Resistive Load',None,'Inductive Load'],
            ['Rated load','10A at 250V AC','5A at 220V AC','2A at 220V AC'],
            ['Electrical endurance','100000 operations','500000 operations','200000 operations']])
    t['boxes'][0][1]=(20,0,60,10);t['boxes'][1][1]=(20,10,60,20)
    return t


def test_nested_headers_keep_all_alternatives_and_endurance():
    facts=column_ratings(nested(),('AB-GS',(0,0,50,5)),7)
    assert len(facts)==3
    assert any('500000' in ' '.join(f['conditions']) and f['value']=='5A at 220V AC' for f in facts)
    t=nested();t['boxes'][0][1]=(20,0,40,10)
    assert len(column_ratings(t,('AB-GS',(0,0,50,5)),7))==2


def rating_hit():
    facts=column_ratings(nested(),('AB-GS',(0,0,50,5)),7)
    return SearchHit('d:7','d','arbitrary.pdf',7,
        'AB-GS 2 poles 4 poles Rated load Resistive Load Inductive Load',.95,
        metadata={'structured_facts':facts,'linked_models':['AB-GS'],'evidence_unit':'page'})


def test_gate_selects_requested_pole_and_load_before_approving():
    h=rating_hit();q='AB-GSの2極形の抵抗負荷時の接点定格は？'
    check=check_evidence(q,[h])
    assert check.supported
    chosen=check.details[0]['matched_facts']
    assert {f['value'] for f in chosen}=={'10A at 250V AC','5A at 220V AC'}
    assert not check_evidence('AB-GSの4極形の抵抗負荷時の接点定格は？',[h]).supported
    assert not check_evidence('AB-GSの2極形の誘導負荷時の接点定格は？',[h]).supported
    assert not check_evidence('AB-GSの3極形の接点定格は？',[h]).supported


def test_cross_page_join_requires_citation_and_correct_identity_document():
    facts=link_ratings(model_profiles(profiles(),1),rated_rows(rating_table(),2))[2]
    h=SearchHit('d:2','d','a.pdf',2,'Rated load Resistive load Inductive load NO NC 250V AC 30V DC',.95,
                metadata={'structured_facts':facts,'linked_models':['AX2S']})
    proof=SearchHit('d:1','d','a.pdf',1,'AX1S AX2S Blade Models No. of poles 1 2',.6,
                   metadata={'binding_proof_only':True})
    q='AX2Sの抵抗負荷時の接点定格は？'
    assert check_evidence(q,[h,proof]).supported
    assert not check_evidence(q,[h]).supported
    assert not check_evidence(q,[h,proof],{('d',2)}).supported
    assert not check_evidence(q,[h,replace(proof,document_id='other')]).supported
    no=check_evidence('AX2SのNO接点の抵抗負荷時の接点定格は？',[h,proof])
    assert no.supported and all('NO' in f['conditions'] for d in no.details for f in d.get('matched_facts',[]))


def test_service_passes_only_approved_conditions_to_answer(tmp_path,keyword_embedder):
    from panel_rag.service import RAGService
    from panel_rag.registry import DocumentRegistry
    from panel_rag.llm import ExtractiveAnswerProvider
    class Store:
        def search_evidence(self,*args,**kwargs): return [rating_hit()]
    service=RAGService(embedder=keyword_embedder,vector_store=Store(),
        registry=DocumentRegistry(tmp_path/'r.json'),uploads_dir=tmp_path/'uploads',answer_provider=ExtractiveAnswerProvider())
    answer=service.ask('AB-GSの2極形の抵抗負荷時の接点定格は？')
    assert answer.answerable
    assert '10A at 250V AC' in answer.answer and '5A at 220V AC' in answer.answer
    assert '2A at 220V AC' not in answer.answer and '4 poles' not in answer.answer


def test_series_subjects_are_shared_without_promoting_prose_to_models():
    assert subjects('AB-GSとZX-100を比較')==['zx-100','ab-gs']
    assert subjects('Please read the manual')==[]


def test_identity_page_is_cited_without_presenting_unrelated_values_as_answer():
    from panel_rag.llm import ExtractiveAnswerProvider
    from panel_rag.models import AnswerContext
    h=SearchHit('d:1','d','proof.pdf',1,'AX1S 100A AX2S 8A',.5,metadata={'binding_proof_only':True})
    result=ExtractiveAnswerProvider().generate('AX2Sの接点定格は？',[AnswerContext('S1',h)])
    assert result.citation_ids==['S1']
    assert '100A' not in result.answer and '原文は出典欄' in result.answer
