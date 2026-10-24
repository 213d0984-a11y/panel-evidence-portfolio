from dataclasses import replace
import pytest
from panel_rag.catalog_tables import row_code_facts
from panel_rag.evidence import check_evidence
from panel_rag.lexical import identifiers,linked_identifier_present
from panel_rag.models import SearchHit


def table():
    rows=[['Catalog Code\nZX80\nooooo','Output Amps',None,'Frame'],
          [None,'ND','HD',None],
          ['C002','2.4','1.8','2.1'],['1004AB','4.8','3.6','3.2']]
    boxes=[[(0,0,20,10),(20,0,60,10),None,(60,0,80,20)],
           [None,(20,10,40,20),(40,10,60,20),None],
           [(i*20,20,(i+1)*20,30) for i in range(4)],
           [(i*20,30,(i+1)*20,40) for i in range(4)]]
    return rows,boxes


def test_row_code_requires_exact_prefix_and_suffix():
    rows,boxes=table()
    facts=row_code_facts(rows,boxes,['ZX80 C002','ZX80 1004AB'])
    assert [(f['model'],f['value']) for f in facts]==[
        ('ZX80 C002','2.4A'),('ZX80 C002','1.8A'),('ZX80 C002','2.1'),
        ('ZX80 1004AB','4.8A'),('ZX80 1004AB','3.6A'),('ZX80 1004AB','3.2')]
    assert all(len(f['source_cells'])==4 for f in facts)
    assert row_code_facts(rows,boxes,['ZX81 C002','ZX80 C0020'])==[]


def test_missing_merged_header_geometry_is_not_guessed():
    rows,boxes=table()
    boxes[0][1]=(20,0,40,10) # heading no longer covers the HD data column
    facts=row_code_facts(rows,boxes,['ZX80 C002'])
    assert not any(f['conditions']==['HD'] for f in facts)


def test_duplicate_suffix_rows_are_ambiguous():
    rows,boxes=table()
    rows.append(rows[2]); boxes.append(boxes[2])
    assert row_code_facts(rows,boxes,['ZX80 C002'])==[]


def test_linked_model_and_both_duty_values_are_required():
    rows,boxes=table()
    facts=row_code_facts(rows,boxes,['ZX80 C002'])
    h=SearchHit('c','d','another.pdf',1,'Catalog Code ZX80\nND HD\nC002 2.4 1.8 2.1',.9,
                metadata={'structured_facts':facts,'linked_models':['ZX80 C002']})
    q='ZX80 C002のND出力電流、HD出力電流、フレーム番号は？'
    assert check_evidence(q,[h]).supported
    assert linked_identifier_present('ZX80-C002',h)
    partial=replace(h,metadata={**h.metadata,'structured_facts':[f for f in facts if 'HD' not in f['conditions']]})
    assert not check_evidence(q,[partial]).supported
    assert not check_evidence('ZX80 C002のBluetooth通信速度は？',[h]).supported


@pytest.mark.parametrize('value,expected',[
    ('ZX80 C002',['zx80-c002']),('ZX80 1004AB',['zx80-1004ab']),
    ('ZX80 60W',['zx80','60w']),('DC24V ZX80',['dc24v','zx80']),
])
def test_prefix_suffix_and_quantities(value,expected):
    assert identifiers(value)==expected


def test_series_namespace_does_not_create_an_extra_requested_model():
    h=SearchHit('c','d','another.pdf',1,'FAMILY-9 / ZX80-C002 Output voltage 24V',.9)
    assert check_evidence('FAMILY-9のZX80-C002の出力電圧は？',[h]).supported


def test_lost_code_cell_geometry_does_not_create_a_link():
    rows,boxes=table()
    boxes[2][0]=None
    assert row_code_facts(rows,boxes,['ZX80 C002'])==[]


def test_parser_failure_retains_source_without_model_link(tmp_path):
    from panel_rag.catalog_tables import CatalogEvidence
    bad=tmp_path/'invalid.pdf'
    bad.write_bytes(b'not a PDF')
    h=SearchHit('c','d','another.pdf',1,'ZX80\nC002',.9)
    result=CatalogEvidence(lambda _:bad).enrich('ZX80 C002の出力電流は？',h)
    assert result.text==h.text
    assert 'linked_models' not in result.metadata
    assert result.metadata['table_link_error']


def test_unknown_additional_property_does_not_authorize_partial_answer():
    h=SearchHit('c','d','another.pdf',1,'AX-101 Output voltage 24V',.9)
    assert not check_evidence('AX-101の出力電圧と光学解像度は？',[h]).supported
    assert not check_evidence('AX-101の光学解像度と出力電圧は？',[h]).supported
    assert check_evidence('AX-101の型式と出力電圧は？',[h]).supported


def test_response_format_is_not_an_additional_specification():
    h=SearchHit('c','d','another.pdf',1,'AX-101 Output voltage 24V',.9)
    assert check_evidence('AX-101の出力電圧を数値と単位付きで教えて',[h]).supported


def test_wildcard_standard_series_is_a_comparison_operand():
    h=SearchHit('c','d','another.pdf',1,'AX3-@-UL Standard model Supply voltage 12V\nBX-104 Supply voltage 24V',.9)
    assert check_evidence('AX3-□-UL標準形とBX-104の電源電圧を比較',[h]).supported


def test_known_ripple_property_still_needs_a_value():
    h=SearchHit('c','d','another.pdf',1,'AX-101 Supply voltage 24V Ripple 2% max.',.9)
    assert check_evidence('AX-101の電源電圧とリップルは？',[h]).supported
    assert not check_evidence('AX-101の電源電圧と光学解像度は？',[h]).supported


def test_sensing_distance_is_not_a_communication_range():
    h=SearchHit('c','d','another.pdf',1,'AX-101 Zigbee enabled. Sensing distance 20mm',.9)
    assert not check_evidence('AX-101のZigbee通信距離は？',[h]).supported


def test_acceptance_criterion_requires_a_limit_not_just_typical_value():
    def hit(text): return SearchHit('c','d','another.pdf',1,text,.9)
    q='AX-101の絶縁抵抗と合格基準は？'
    assert check_evidence(q,[hit('AX-101 Insulation resistance 200 MΩ minimum')]).supported
    assert not check_evidence(q,[hit('AX-101 Insulation resistance 200 MΩ typical')]).supported


def test_unknown_property_before_model_is_not_dropped():
    h=SearchHit('c','d','another.pdf',1,'AX-101 Output voltage 24V',.9)
    assert not check_evidence('optical resolution of AX-101 and output voltage?', [h]).supported


def test_same_filename_does_not_combine_different_documents():
    hits=[SearchHit('a','doc-a','spec.pdf',1,'AX-101 Product overview',.9),
          SearchHit('b','doc-b','spec.pdf',1,'BX-202 Output voltage 24V',.9)]
    assert not check_evidence('AX-101の出力電圧は？',hits).supported


def test_citation_identity_is_document_id_not_filename():
    hits=[SearchHit('a','doc-a','spec.pdf',1,'AX-101 Product overview',.9),
          SearchHit('b','doc-b','spec.pdf',1,'AX-101 Output voltage 24V',.9)]
    q='AX-101の出力電圧は？'
    assert check_evidence(q,hits).supported
    assert not check_evidence(q,hits,{('doc-a',1)}).supported
    assert not check_evidence(q,hits,{('spec.pdf',1)}).supported
    assert check_evidence(q,hits,{('doc-b',1)}).supported
