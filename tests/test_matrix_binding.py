from copy import deepcopy
from panel_rag.matrix_binding import join_tables,catalogue_identities,quantity,explicit_model_facts
from dataclasses import replace
from panel_rag.evidence import check_evidence
from panel_rag.models import SearchHit
from panel_rag.retrieval import evidence_pages


def catalogue():
    rows=[['Model number','Output Voltage (VDC)','Output current'],
          ['AG7-40','24 V','3 A'],['AG7-50','48 V','2 A']]
    boxes=[[(i*20,r*10,(i+1)*20,(r+1)*10) for i in range(3)] for r in range(3)]
    return dict(rows=rows,boxes=boxes,words=[])


def matrix():
    rows=[['Item','Output voltage (VDC)','24 V','48 V'],
          ['Output','Rated output current','3 A','2 A'],
          ['Input','Voltage range','80 to 260 VAC',None],
          ['Environment','Ambient operating temperature','-30 to 65°C',None],
          ['Construction','Degree of protection','IP40',None]]
    boxes=[[(i*20,r*10,(i+1)*20,(r+1)*10) for i in range(4)] for r in range(5)]
    for r in [2,3,4]: boxes[r][2]=(40,r*10,80,(r+1)*10); boxes[r][3]=None
    return dict(rows=rows,boxes=boxes)


def pages(cat=None,spec=None,series='AG7'):
    return [dict(page=1,series='AG7',tables=[cat or catalogue()]),
            dict(page=2,series=series,tables=[spec or matrix()])]


def test_unique_two_anchor_join_keeps_conditions_and_both_pages():
    facts=join_tables(pages())[2]
    subject=[f for f in facts if f['model']=='AG7-40']
    assert {f['property'] for f in subject}=={'output_current','input_voltage','temperature','protection'}
    assert next(f['value'] for f in subject if f['property']=='temperature')=='-30 to 65°C'
    assert all(f['binding']['page']==1 and len(f['binding']['source_cells'])==3 for f in subject)
    assert all(len(f['binding']['matrix_cells'])==2 for f in subject)


def test_matching_voltage_alone_cannot_join_a_different_current():
    cat=catalogue(); cat['rows'][1][2]='4 A'
    facts=join_tables(pages(cat=cat))[2]
    assert not any(f['model']=='AG7-40' for f in facts)


def test_two_models_with_the_same_key_are_ambiguous():
    cat=catalogue(); cat['rows'].append(['AG7-41','24 V','3 A']); cat['boxes'].append(cat['boxes'][1])
    assert not any(f['model']=='AG7-40' for f in join_tables(pages(cat=cat))[2])


def test_repeated_matrix_columns_and_different_heading_are_not_inferred():
    p=pages(); p.append(dict(page=3,series='AG7',tables=[deepcopy(matrix())]))
    assert join_tables(p)=={}
    assert join_tables(pages(series='AG8'))=={}
    p=pages(); p[0]['series']=None
    assert join_tables(p)=={}


def test_empty_cell_does_not_inherit_without_physical_span():
    spec=matrix(); spec['boxes'][3][2]=(40,30,60,40)
    facts=join_tables(pages(spec=spec))[2]
    assert any(f['model']=='AG7-40' and f['property']=='temperature' for f in facts)
    assert not any(f['model']=='AG7-50' and f['property']=='temperature' for f in facts)


def test_misaligned_anchor_columns_cannot_create_a_join():
    spec=matrix(); spec['boxes'][1][2]=(41.5,10,61.5,20)
    facts=join_tables(pages(spec=spec))[2]
    assert not any(f['model']=='AG7-40' for f in facts)


def test_model_projection_uses_two_aligned_rows_not_a_neighbour():
    cat=catalogue(); cat['rows'][1][0]=None; cat['boxes'][1][0]=None
    cat['words']=[(1,11,19,19,'AG7-40')]
    assert any(r['model']=='AG7-40' for r in catalogue_identities(cat,'AG7',1))
    cat['words']=[(1,21,19,29,'AG7-40')]
    assert not any(r['model']=='AG7-40' for r in catalogue_identities(cat,'AG7',1))
    cat['words']=[(1,11,19,19,'AG7-40')]; cat['boxes'][1][2]=(40,12,60,20)
    assert not any(r['model']=='AG7-40' for r in catalogue_identities(cat,'AG7',1))


def test_quantities_are_not_decoded_from_model_numbers():
    assert quantity('24 V','voltage','Output voltage (VDC)')==('24','vdc')
    assert quantity('3000 mA','current')==('3','a')
    assert quantity('AG7-24','voltage') is None
    assert quantity('24/48 V','voltage') is None
    assert quantity('3 A typ.','current') is None


def explicit_table():
    rows=[['Model','AG7-05','BG7-05','CG7-05'],[None,'AG7-24','BG7-24','CG7-24'],
          ['Rated Input Voltage','90 to 260VAC',None,None],
          ['Operating Temperature (No freezing)','-20 to 75°C',None,'-20 to 60°C'],
          ['Degree of protection','IP40',None,None]]
    boxes=[[(i*20,r*10,(i+1)*20,(r+1)*10) for i in range(4)] for r in range(5)]
    boxes[0][0]=(0,0,20,20); boxes[1][0]=None
    for r in [2,4]: boxes[r][1]=(20,r*10,80,(r+1)*10); boxes[r][2]=boxes[r][3]=None
    boxes[3][1]=(20,30,60,40); boxes[3][2]=None
    return dict(rows=rows,boxes=boxes)


def test_explicit_model_header_rows_and_merged_value_range():
    facts=explicit_model_facts(explicit_table(),2)
    assert next(f['value'] for f in facts if f['model']=='BG7-24' and f['property']=='temperature')=='-20 to 75°C'
    assert next(f['value'] for f in facts if f['model']=='CG7-24' and f['property']=='temperature')=='-20 to 60°C'
    assert all(f['binding']['page']==2 for f in facts)


def test_explicit_header_must_cover_the_model_row():
    table=explicit_table(); table['boxes'][0][0]=(0,0,20,10)
    assert not any(f['model']=='BG7-24' for f in explicit_model_facts(table,2))


def test_explicit_merged_value_does_not_fill_an_uncovered_column():
    table=explicit_table(); table['boxes'][3][1]=(20,30,40,40)
    assert not any(f['model']=='BG7-24' and f['property']=='temperature' for f in explicit_model_facts(table,2))


def test_conflicting_rows_for_same_model_are_not_disambiguated_by_question():
    cat=catalogue(); cat['rows'][2][0]='AG7-40'
    assert join_tables(pages(cat=cat))=={}


def linked_hits():
    facts=[f for f in join_tables(pages())[2] if f['model']=='AG7-40']
    spec=SearchHit('d:page-2:chunk-0','d','same.pdf',2,
                   'AG7\nAmbient operating temperature -30 to 65°C\nDegree of protection IP40\nOptical resolution 80mm',.95,
                   metadata={'linked_models':['AG7-40'],'structured_facts':facts,'required_source_pages':[1]})
    proof=SearchHit('d:page-1:chunk-0','d','same.pdf',1,'AG7-40 Output voltage 24 V Output current 3 A',.4,
                    metadata={'binding_proof_only':True})
    return spec,proof


def test_join_requires_the_actual_identity_page_in_retrieval_and_citation():
    spec,proof=linked_hits(); q='AG7-40の使用周囲温度範囲と保護等級は？'
    assert check_evidence(q,[spec,proof]).supported
    assert not check_evidence(q,[spec]).supported
    assert not check_evidence(q,[spec,proof],{('d',2)}).supported
    assert check_evidence(q,[spec,proof],{('d',1),('d',2)}).supported
    wrong=replace(proof,text='AG7-41 Output voltage 24 V Output current 3 A')
    assert not check_evidence(q,[spec,wrong]).supported
    wrong_doc=replace(proof,document_id='other')
    assert not check_evidence(q,[spec,wrong_doc]).supported


def test_a_linked_field_cannot_donate_other_properties_on_the_matrix_page():
    spec,proof=linked_hits()
    assert not check_evidence('AG7-40の検出距離は？',[spec,proof]).supported


def test_conflicting_values_for_same_bound_condition_are_not_selected_arbitrarily():
    spec,proof=linked_hits()
    contradictory=deepcopy(next(f for f in spec.metadata['structured_facts'] if f['property']=='temperature'))
    contradictory['value']='-30 to 80°C'
    spec=replace(spec,metadata={**spec.metadata,'structured_facts':spec.metadata['structured_facts']+[contradictory]})
    assert not check_evidence('AG7-40の使用周囲温度範囲は？',[spec,proof]).supported


def test_pole_variant_is_a_required_qualifier_not_a_mention_elsewhere():
    def hit(text): return SearchHit('x','x','relay.pdf',1,text,.95)
    q='AB-GSの2極形の抵抗負荷時の接点定格は？'
    assert check_evidence(q,[hit('AB-GS 2 poles Contact rating Resistive load 6A at 250V')]).supported
    assert not check_evidence(q,[hit('AB-GS 4 poles Contact rating Resistive load 6A at 250V')]).supported
    assert not check_evidence(q,[hit('AB-GS 2 poles 4 poles Contact rating Resistive load 6A at 250V')]).supported
    assert not check_evidence(q,[hit('AB-GS 2 poles overview '+('Introduction '*60)+'Contact rating Resistive load 6A at 250V')]).supported


def test_retrieval_budget_includes_proof_pages_and_preserves_dense_scores():
    spec,proof=linked_hits(); q='AG7-40の使用周囲温度範囲と保護等級は？'
    selected=evidence_pages(q,[spec,proof],2,.72)
    assert [p.page_number for p in selected]==[2,1]
    assert selected[1].score==.4
    assert check_evidence(q,selected).supported
    limited=evidence_pages(q,[spec,proof],1,.72)
    assert len(limited)<=1
    assert not check_evidence(q,limited).supported


def test_refusal_safety_does_not_remove_a_requested_product_from_retrieval():
    q='AX-401とBX-501の通信速度を比較'
    hits=[SearchHit(f'a:page-{i}:chunk-0','a','a.pdf',i,'AX-401 product overview',.9) for i in range(1,8)]
    hits.append(SearchHit('b:page-1:chunk-0','b','b.pdf',1,'BX-501 product overview',.9))
    selected=evidence_pages(q,hits,2,.72)
    assert {h.document_id for h in selected}=={'a','b'}
    assert not check_evidence(q,selected).supported


def test_citation_gate_and_provider_cannot_omit_the_identity_proof(tmp_path,keyword_embedder):
    from panel_rag.service import RAGService
    from panel_rag.registry import DocumentRegistry
    from conftest import StubProvider
    class Store:
        def search_evidence(self,*args,**kwargs): return list(linked_hits())
    service=RAGService(embedder=keyword_embedder,vector_store=Store(),
                       registry=DocumentRegistry(tmp_path/'documents.json'),uploads_dir=tmp_path/'uploads',
                       answer_provider=StubProvider(citation_ids=['S1']))
    q='AG7-40の使用周囲温度範囲と保護等級は？'
    assert not service.ask(q).answerable
    service.answer_provider=StubProvider(citation_ids=['S1','S2'])
    answer=service.ask(q)
    assert answer.answerable
    assert {c.hit.page_number for c in answer.citations}=={1,2}
    assert {f['property'] for f in answer.citations[0].hit.metadata['structured_facts']}=={'temperature','protection'}
