from copy import deepcopy
from dataclasses import replace
from panel_rag.evidence import check_evidence
from panel_rag.models import SearchHit,AnswerContext
from panel_rag.matrix_binding import explicit_model_facts
from panel_rag.table_context import contextualize,with_conditions,note_definitions
from panel_rag.llm import ExtractiveAnswerProvider


def word(text,x,y,block=0,line=0): return (x,y,x+len(text)*.8,y+5,text,block,line,0)


def broken_table():
    # A grid extractor has mistaken the entire table frame for the MODEL
    # label cell. Data/model cells themselves are still physically drawn.
    rows=[['MODEL plus incorrectly captured body',None,'ZX4-05','ZX4-24'],
          [None,'DC VOLTAGE','5V','24V'],[None,'RATED CURRENT','7A','2A'],
          [None,'RATED POWER','35W','48W'],[None,'VOLTAGE ADJ. RANGE','4.8 to 5.2V','22 to 28V'],
          [None,'WORKING TEMP.','-30 to +70°C (Refer to Derating Curve)',None]]
    boxes=[[(c*30,r*10,(c+1)*30,(r+1)*10) if v else None for c,v in enumerate(row)] for r,row in enumerate(rows)]
    boxes[0][0]=(0,0,120,60);boxes[5][2]=(60,50,120,60)
    return dict(rows=rows,boxes=boxes,bbox=(0,0,120,60),
                words=[word('MODEL',1,2),word('OUTPUT',1,22),word('ZX4-05',61,2),word('ZX4-24',91,2)],
                horizontal_rules=[((0,10),(120,10)),((0,50),(120,50))])


def hit(facts,text='ZX4-05 ZX4-24 MODEL OUTPUT'):
    return SearchHit('d:2','d','arbitrary.pdf',2,text,.95,metadata={'structured_facts':facts,'evidence_unit':'page'})


def test_header_recovery_needs_a_literal_word_in_aligned_model_row():
    original=broken_table();t=contextualize(original)
    assert t['rows'][0][0]=='MODEL' and original['rows'][0][0]!='MODEL'
    assert len(t['header_words'][0])==1
    t=broken_table();t['words'][0]=word('OVERVIEW',1,2)
    assert explicit_model_facts(contextualize(t),2)==[]
    t=broken_table();t['boxes'][0][3]=(90,3,120,13)
    assert explicit_model_facts(contextualize(t),2)==[]


def test_output_group_needs_full_width_rules_not_nearby_output_word():
    facts=explicit_model_facts(contextualize(broken_table()),2)
    assert next(f['value'] for f in facts if f['model']=='ZX4-05' and f['property']=='power')=='35W'
    assert next(f['value'] for f in facts if f['model']=='ZX4-24' and f['property']=='output_current')=='2A'
    t=broken_table();t['horizontal_rules']=[((30,10),(120,10)),((30,50),(120,50))]
    assert not any(f['property']=='power' for f in explicit_model_facts(contextualize(t),2))
    t=broken_table();t['words'].append(word('INPUT',1,32))
    assert not any(f['property']=='output_current' for f in explicit_model_facts(contextualize(t),2))


def test_power_alias_and_adjustment_range_are_separate_from_nominal_voltage():
    facts=explicit_model_facts(contextualize(broken_table()),2);h=hit(facts)
    assert check_evidence('ZX4-05の定格出力電力は何Wですか。',[h]).supported
    check=check_evidence('ZX4-24の出力電圧調整範囲は？',[h])
    assert check.supported and check.requirements==['output_voltage_adjustment']
    selected=[f for d in check.details for f in d['matched_facts']]
    assert {f['value'] for f in selected}=={'22 to 28V'}
    h.metadata['structured_facts']=[f for f in facts if f['property']=='output_voltage']
    assert not check_evidence('ZX4-24の出力電圧調整範囲は？',[h]).supported


def test_applicability_conditions_must_belong_to_each_accepted_property():
    facts=with_conditions(explicit_model_facts(contextualize(broken_table()),2),[],2);h=hit(facts)
    assert check_evidence('ZX4-24の使用周囲温度範囲と適用条件は？',[h]).supported
    assert not check_evidence('ZX4-24の定格出力電力と適用条件は？',[h]).supported
    assert not check_evidence('ZX4-99の使用周囲温度範囲と適用条件は？',[h]).supported
    assert not check_evidence('ZX4-24の通信速度と適用条件は？',[h]).supported
    assert not check_evidence('ZX4-24とZX4-99の使用周囲温度範囲と適用条件は？',[h]).supported
    assert check_evidence('ZX4-24 operating temperature and applicability conditions',[h]).supported


def test_footnotes_are_explicit_and_decimal_values_are_not_note_definitions():
    words=[word('1.5A',1,1),word('Note 1: Input fuse required.',1,60,2,0),
           word('Note 9: See output derating curves.',1,70,2,1)]
    notes=note_definitions(words)
    assert notes['1']['text'].startswith('Note 1:')
    facts=explicit_model_facts(contextualize(broken_table()),2)
    fact=deepcopy(next(f for f in facts if f['model']=='ZX4-24' and f['property']=='temperature'))
    fact.update(original_label='Operating Temperature9 (No freezing)',original_value='-25 to +75°C',value='-25 to +75°C')
    linked=with_conditions([fact],words,2)[0]
    assert 'Note 9: See output derating curves.' in linked['conditions']
    assert linked['condition_sources'][0]['page']==2
    result=ExtractiveAnswerProvider().generate('ZX4-24の使用周囲温度は？',[AnswerContext('S1',hit([linked]))])
    assert '75°C' in result.answer and 'derating curves' in result.answer


def test_unresolved_or_duplicate_footnote_cannot_authorize_answer():
    fact=deepcopy(next(f for f in explicit_model_facts(contextualize(broken_table()),2) if f['property']=='temperature'))
    fact.update(original_label='Operating Temperature9',original_value='-25 to +75°C',value='-25 to +75°C')
    missing=with_conditions([deepcopy(fact)],[],2)
    assert not check_evidence(fact['model']+'の使用周囲温度は？',[hit(missing)]).supported
    words=[word('Note 9: See derating.',1,60,2,0),word('Note 9: Different condition.',1,70,2,1)]
    ambiguous=with_conditions([deepcopy(fact)],words,2)
    assert not check_evidence(fact['model']+'の使用周囲温度は？',[hit(ambiguous)]).supported


def test_conditions_on_other_model_cannot_cover_comparison_side():
    facts=with_conditions(explicit_model_facts(contextualize(broken_table()),2),[],2)
    for f in facts:
        if f['model']=='ZX4-05' and f['property']=='temperature': f['conditions']=[]
    assert not check_evidence('ZX4-05とZX4-24の使用周囲温度範囲と適用条件は？',[hit(facts)]).supported


def test_known_power_does_not_authorize_unknown_field_or_missing_comparison_half():
    facts=explicit_model_facts(contextualize(broken_table()),2)
    assert not check_evidence('ZX4-24の定格出力電力と光学解像度は？',[hit(facts)]).supported
    facts=[f for f in facts if not (f['model']=='ZX4-05' and f['property']=='output_current')]
    assert not check_evidence('ZX4-05とZX4-24の定格出力電流を比較してください。',[hit(facts)]).supported


def test_asterisk_notes_keep_same_block_continuations_not_reference_markers():
    words=[word('*7) a reference, not a definition',1,1,0,0),
           word('*7 Refer to derating.',1,70,2,0),word('Only with the stated mounting.',1,80,2,1)]
    notes=note_definitions(words)
    assert notes['7']['text']=='*7 Refer to derating. Only with the stated mounting.'


def test_neighboring_column_words_cannot_authorize_or_hide_a_table_group():
    t=broken_table();t['words'][1]=word('OUTPUT',-40,22)
    assert not any(f['property']=='power' for f in explicit_model_facts(contextualize(t),2))
    t=broken_table();t['words'].append(word('INPUT',-40,22))
    assert any(f['property']=='power' for f in explicit_model_facts(contextualize(t),2))


def test_a_standard_reference_is_not_an_applicability_condition():
    fact=deepcopy(next(f for f in explicit_model_facts(contextualize(broken_table()),2) if f['model']=='ZX4-24'))
    fact.update(property='protection',value='IP20',original_label='Degree of protection',conditions=['EN60529'])
    assert not check_evidence('ZX4-24の保護等級と適用条件は？',[hit([fact])]).supported
    fact['conditions'].append('Only with the specified mounting')
    assert check_evidence('ZX4-24の保護等級と適用条件は？',[hit([fact])]).supported
