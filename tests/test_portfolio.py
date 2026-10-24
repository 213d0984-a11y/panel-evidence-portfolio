import pytest
from panel_rag.tables import model_column_facts
from panel_rag.evidence import check_evidence
from panel_rag.models import SearchHit


def test_exact_model_column_not_neighbor_or_merged_cell():
    rows=[['Model','AX-101','AX-102'],['Current','2A','4A'],['Voltage','24V',None]]
    facts=model_column_facts(rows,['AX102'])
    assert [(f['property'],f['value']) for f in facts]==[('Current','4A')]
    assert model_column_facts(rows,['AX-10'])==[]


def test_duplicate_model_headers_are_ambiguous():
    assert model_column_facts([['Model','AX-101','AX-101'],['Current','2A','4A']],['AX-101'])==[]


def test_single_model_is_not_guessed_as_a_comparison_table():
    assert model_column_facts([['Model','AX-101'],['Current','2A']],['AX-101'])==[]


def test_certified_rating_does_not_prove_general_contact_rating():
    h=SearchHit('c','d','unseen.pdf',1,'AX-101 Certified Ratings\nContact ratings 4A 250V',.9)
    assert not check_evidence('AX-101の接点定格は？',[h]).supported
    assert check_evidence('AX-101の認証接点定格は？',[h]).supported


def test_remote_component_name_cannot_qualify_another_components_torque():
    text='AX-101 DIN rail mounting instructions. '+('Installation instructions. '*20)+'\nPower terminals tightening torque 2Nm'
    h=SearchHit('c','d','unseen.pdf',1,text,.9)
    assert not check_evidence('AX-101のDINレール固定ねじの締付トルクは？',[h]).supported
    assert check_evidence('AX-101の電源端子の締付トルクは？',[h]).supported


def test_value_first_humidity_clause():
    h=SearchHit('c','d','unseen.pdf',1,'AX-101 operates between 15% and 80% relative humidity.',.9)
    assert check_evidence('AX-101の使用周囲湿度は？',[h]).supported


@pytest.mark.parametrize('model',['AX7.301','AX7.301-C2','RX4.88'])
def test_dotted_model_is_not_a_property_qualifier(model):
    h=SearchHit('c','d','unseen.pdf',1,model+' Operating temperature -10 to 50°C',.9)
    assert check_evidence(model+'の使用周囲温度範囲は？',[h]).supported


def test_load_condition_cannot_be_inferred_from_a_generic_contact_rating():
    def hit(text): return SearchHit('c','d','unseen.pdf',1,text,.9)
    q='AX-101の抵抗負荷時の接点定格は？'
    assert not check_evidence(q,[hit('AX-101 Contact ratings 4A 250V')]).supported
    assert check_evidence(q,[hit('AX-101 Contact ratings Resistive load 4A 250V')]).supported


def test_distinct_subject_clauses_require_both_sources():
    panel=SearchHit('p','p','a.pdf',1,'配電盤\n電源の定格出力 24V 8A',.9)
    sensor=SearchHit('s','s','b.pdf',1,'VS-111 電源電圧 12V',.9)
    q='配電盤の電源定格と、VS-111の電源電圧は？'
    assert check_evidence(q,[panel,sensor]).supported
    assert not check_evidence(q,[sensor]).supported


def test_declared_output_rating_can_express_current_without_repeating_word_current():
    h=SearchHit('c','d','unseen.pdf',1,'AX-101 定格出力 DC24V 8A',.9)
    assert check_evidence('AX-101の定格出力電流は？',[h]).supported


def test_property_list_is_not_mistaken_for_an_unnamed_product():
    h=SearchHit('c','d','unseen.pdf',1,'使用周囲温度 -5～50℃\n相対湿度 20～80%',.9)
    assert check_evidence('使用周囲温度と湿度の条件は？',[h]).supported


def test_explicit_alphabetic_series_can_use_numbered_family_members():
    h=SearchHit('c','d','unseen.pdf',1,'Enclosure models AB1-20 and AB2-30\nAmbient temperature -10 to 40°C',.9)
    assert check_evidence('ABシリーズの使用周囲温度は？',[h]).supported
    assert not check_evidence('AXシリーズの使用周囲温度は？',[h]).supported


def test_series_prefix_does_not_match_a_different_letter_prefix():
    from panel_rag.lexical import identifier_present
    assert identifier_present('AB','AB2-30')
    assert not identifier_present('AB','ABX2-30')
    assert not identifier_present('AB2-30','AB2-300')
