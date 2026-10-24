from copy import deepcopy
from panel_rag.matrix_binding import projected_model_facts
from panel_rag.evidence import check_evidence
from panel_rag.models import SearchHit


def table():
    rows=[['MODEL',None,'XY4-24','XY4-48'],['OUTPUT','VOLTAGE[V]\nCURRENT[A]', '24','48'],
          [None,None,'4.5','2.1'],['Environment','OPERATING TEMP.\nSTORAGE TEMP.','-10 to +71C (Refer to Derating)',None],
          [None,None,'-20 to +75C',None]]
    boxes=[[(c*30,r*10,(c+1)*30,(r+1)*10) if v else None for c,v in enumerate(row)] for r,row in enumerate(rows)]
    boxes[0][0]=(0,0,60,10); boxes[1][0]=(0,10,30,30); boxes[1][1]=(30,10,60,30)
    boxes[3][0]=(0,30,30,50);boxes[3][1]=(30,30,60,50)
    boxes[3][2]=(60,30,120,40);boxes[4][2]=(60,40,120,50)
    words=[(31,11,59,19,'VOLTAGE[V]'),(31,21,59,29,'CURRENT[A]'),
           (31,31,59,39,'OPERATING TEMP.'),(31,41,59,49,'STORAGE TEMP.')]
    return dict(rows=rows,boxes=boxes,words=words)


def test_merged_label_cell_uses_drawn_row_band_and_explicit_model_column():
    facts=projected_model_facts(table(),3)
    assert next(f['value'] for f in facts if f['model']=='XY4-48' and f['property']=='output_current')=='2.1 A'
    assert next(f['value'] for f in facts if f['model']=='XY4-24' and f['property']=='output_voltage')=='24 V'
    assert next(f['original_value'] for f in facts if f['model']=='XY4-24' and f['property']=='output_current')=='4.5'


def test_no_column_fill_or_nearest_label_inference():
    t=table();t['boxes'][3][2]=(60,30,90,40)
    assert not any(f['model']=='XY4-48' and f['property']=='temperature' for f in projected_model_facts(t,3))
    t=table();t['words'][1]=(31,10,59,19,'CURRENT[A]')
    assert not any(f['property']=='output_current' for f in projected_model_facts(t,3))
    t=table();t['rows'][0][0]='Overview'
    assert projected_model_facts(t,3)==[]


def test_input_and_output_current_cannot_be_interchanged():
    t=table(); t['rows'][1][0]='INPUT'
    facts=projected_model_facts(t,3)
    assert {f['property'] for f in facts}>={'input_voltage','current'}
    assert not any(f['property']=='output_current' for f in facts)


def test_operating_and_storage_temperatures_and_missing_degree_glyph():
    facts=projected_model_facts(table(),3)
    h=SearchHit('d3','d','example.pdf',3,'XY4-24 XY4-48 Operating temp. Storage temp.',.95,
                metadata={'structured_facts':facts})
    operating=check_evidence('XY4-24の動作温度範囲は？',[h])
    assert operating.supported
    assert {f['property'] for f in operating.details[0]['matched_facts']}=={'temperature'}
    storage=check_evidence('XY4-24の保存温度は？',[h])
    assert storage.supported
    assert {f['property'] for f in storage.details[0]['matched_facts']}=={'storage_temperature'}
    only_operating=[f for f in facts if f['property']=='temperature']
    h.metadata['structured_facts']=only_operating
    assert not check_evidence('XY4-24の保存温度は？',[h]).supported


def test_duplicate_headers_define_sections_not_model_options():
    t=table(); other=table()
    offset=60
    t['rows']+=other['rows'];t['boxes']+=[[(b[0],b[1]+offset,b[2],b[3]+offset) if b else None for b in row] for row in other['boxes']]
    t['words']+=[(w[0],w[1]+offset,w[2],w[3]+offset,w[4]) for w in other['words']]
    facts=projected_model_facts(t,1)
    assert len(facts)==16
    h=SearchHit('d1','d','e.pdf',1,'XY4-24 Output current',.95,metadata={'structured_facts':facts})
    assert check_evidence('XY4-24の出力電流は？',[h]).supported
    contradiction=deepcopy(next(f for f in facts if f['model']=='XY4-24' and f['property']=='output_current'))
    contradiction['value']='7 A';h.metadata['structured_facts'].append(contradiction)
    assert not check_evidence('XY4-24の出力電流は？',[h]).supported


def test_model_table_below_long_cover_description_is_not_skipped(monkeypatch):
    from panel_rag.catalog_tables import CatalogEvidence
    facts=projected_model_facts(table(),3)
    monkeypatch.setattr('panel_rag.matrix_binding.read_explicit_page',lambda path,n:facts)
    h=SearchHit('d3','d','example.pdf',3,('Product description '*100)+'MODEL XY4-24 XY4-48',.95)
    enriched=CatalogEvidence(lambda document:'registered.pdf').enrich_pages('XY4-24の出力電流は？',[h])[0]
    assert check_evidence('XY4-24の出力電流は？',[enriched]).supported


def test_typed_unit_header_handles_ranges_without_borrowing_a_reference_number():
    from dataclasses import replace
    fact=next(f for f in projected_model_facts(table(),3) if f['model']=='XY4-24' and f['property']=='output_voltage')
    fact.update(property='input_voltage',value='AC85 - 265 or DC120 - 370 (see manual 1.1)',unit_header='V')
    h=SearchHit('d3','d','e.pdf',3,'XY4-24 INPUT',.95,metadata={'structured_facts':[fact]})
    assert check_evidence('XY4-24の入力電圧範囲は？',[h]).supported
    fact['value']='See manual 24'
    assert not check_evidence('XY4-24の入力電圧範囲は？',[h]).supported
    fact['value']='85A';fact['unit_header']='A'
    assert not check_evidence('XY4-24の入力電圧範囲は？',[h]).supported
