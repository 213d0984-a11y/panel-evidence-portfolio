from panel_rag.evidence import check_evidence
from panel_rag.lexical import identifiers,identifier_present
from panel_rag.models import SearchHit

def hit(text): return SearchHit('c','d','spec.pdf',1,text,.99)

def test_numeric_model_requires_explicit_type_label():
    assert identifiers('型式72.43の保護等級は？')==['72.43']
    assert identifiers('Type 72.43 protection rating?')==['72.43']
    assert identifiers('温度72.43度')==[]
    assert identifier_present('72.43','72.43/72.53')
    assert not identifier_present('72.43','72.430 72.43.1')

def test_subject_type_label_does_not_authorize_unknown_property():
    h=hit('72.43 Protection category IP20')
    assert not check_evidence('型式72.43の光学解像度は？',[h]).supported
    assert check_evidence('型式72.43の保護等級は？',[h]).supported
    assert not check_evidence('型式72.44の保護等級は？',[h]).supported

def test_unit_before_value_and_next_property_boundary():
    h=hit('72.43 Dielectric strength between open contacts V AC 1200\nAmbient temperature range °C -30...+65\nProtection category IP20')
    assert check_evidence('型式72.43の耐電圧は？',[h]).supported
    assert check_evidence('型式72.43の使用周囲温度範囲は？',[h]).supported
    h=hit('AX-201 Output voltage not specified\nInput voltage 24V')
    assert not check_evidence('AX-201の出力電圧は？',[h]).supported
    h=hit('AX-201 Input voltage 24V\nOutput voltage see manual')
    assert not check_evidence('AX-201の出力電圧は？',[h]).supported

def test_comparison_qualifiers_belong_to_each_subject():
    h=hit('AX-201 ND overload capacity 110%\nBX-301 HD overload capacity 150%')
    assert check_evidence('AX-201のND定格とBX-301のHD定格の過負荷耐量を比較',[h]).supported
    assert not check_evidence('AX-201のHD定格とBX-301のND定格の過負荷耐量を比較',[h]).supported

def test_dielectric_location_cannot_be_borrowed_from_another_part():
    h=hit('72.43 Dielectric strength between input/output V AC 2400')
    assert check_evidence('型式72.43の入力出力間の耐電圧は？',[h]).supported
    assert not check_evidence('型式72.43の開放接点間の耐電圧は？',[h]).supported
    h=hit('AX-201 Mounting screw torque 1Nm')
    assert not check_evidence('AX-201の電源端子の締付トルクは？',[h]).supported
