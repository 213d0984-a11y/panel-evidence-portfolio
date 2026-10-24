from dataclasses import replace
import pytest
from panel_rag.models import SearchHit, AnswerContext
from panel_rag.retrieval import merge_page, evidence_pages
from panel_rag.evidence import check_evidence
from panel_rag.llm import ExtractiveAnswerProvider


def hit(text, page=1, index=0, doc='vendor-a', score=.9):
    return SearchHit(f'{doc}:page-{page}:chunk-{index}', doc, doc+'.pdf', page, text, score)


def test_page_reconstruction_restores_order_and_overlap():
    overlap = ' specification table heading '
    first = hit('QX-812'+overlap)
    second = hit(overlap+'Output voltage 18 V', index=1)
    page = merge_page([second, first])
    assert page.text == 'QX-812'+overlap+'Output voltage 18 V'
    assert len(page.metadata['source_chunk_ids']) == 2


def test_accidental_one_character_overlap_is_not_removed():
    page = merge_page([hit('Input voltage 24V'), hit('Voltage table has more specifications',index=1)])
    assert '24V\nVoltage' in page.text


def test_specification_below_initial_top_five_is_recovered():
    candidates = [hit('QX-812 Product overview',page=p) for p in range(1,15)]
    candidates += [hit('QX-812 Output voltage 18 V',page=15)]
    result = evidence_pages('QX-812の出力電圧は？',candidates,5,.72)
    assert result[0].page_number == 15


def test_comparison_covers_each_model_not_only_dominant_document():
    candidates = [hit('QX-812 Output voltage 18 V',page=p) for p in range(1,10)]
    candidates += [hit('TR-427 Output voltage 30 V',doc='vendor-b')]
    result = evidence_pages('QX-812とTR-427の出力電圧を比較',candidates,2,.72)
    assert {h.document_id for h in result} == {'vendor-a','vendor-b'}
    assert check_evidence('QX-812とTR-427の出力電圧を比較',result).supported


def test_filename_change_does_not_change_evidence_selection():
    candidates=[hit('QX-812 Outline'),hit('QX-812 Output voltage 18 V',page=2)]
    renamed=[replace(h,file_name='unseen-manufacturer.pdf') for h in candidates]
    assert evidence_pages('QX-812の出力電圧は？',candidates,1,.72)[0].text == evidence_pages('QX-812の出力電圧は？',renamed,1,.72)[0].text


@pytest.mark.parametrize('model', ['QX-812','QX-8120','QX-813'])
def test_complete_pages_do_not_substitute_unregistered_models(model):
    result=evidence_pages(model+'の出力電圧は？',[hit('QX-812 Output voltage 18 V')],1,.72)
    assert check_evidence(model+'の出力電圧は？',result).supported == (model=='QX-812')


@pytest.mark.parametrize('series',['AB','XY','LM'])
def test_alphabetic_series_without_digits(series):
    assert check_evidence(series+'シリーズの使用周囲温度は？',[hit(series+' Series Operating temperature -15 to 55°C')]).supported
    assert not check_evidence(series+'シリーズの使用周囲温度は？',[hit('ZZ Series Operating temperature -15 to 55°C')]).supported


def test_extractive_pages_include_late_values_and_all_selected_sources():
    pages=[merge_page([hit('QX-812 '+('Introduction. '*40)+'Output voltage 18 V',page=p)]) for p in range(1,4)]
    contexts=[AnswerContext(f'S{i}',p) for i,p in enumerate(pages,1)]
    result=ExtractiveAnswerProvider().generate('QX-812の出力電圧は？',contexts)
    assert 'Output voltage 18 V' in result.answer
    assert result.citation_ids == ['S1','S2','S3']


@pytest.mark.parametrize('protocol',['Zigbee','CANopen','PROFINET'])
def test_related_product_pages_do_not_prove_unmentioned_protocol(protocol):
    candidates=[hit('QX-812 Output voltage 18 V'),hit('TR-427 '+protocol+' Communication speed 10Mbps',doc='vendor-b')]
    question='QX-812の'+protocol+'通信速度は？'
    result=evidence_pages(question,candidates,2,.72)
    assert not check_evidence(question,result).supported


@pytest.mark.parametrize('unit',['° C','º C','℃'])
def test_degree_glyph_variants_in_unseen_document(unit):
    assert check_evidence('QX-812の使用周囲温度は？',[hit('QX-812 Operating temperature -15 to 55'+unit)]).supported


def test_same_page_other_models_explicit_property_is_not_borrowed():
    page=hit('QX-812 Output voltage 18V\nTR-427 Zigbee Communication speed 10Mbps')
    assert not check_evidence('QX-812のZigbee通信速度は？',[page]).supported


def test_protection_code_is_a_value_not_an_alternate_model():
    assert check_evidence('QX-812の保護構造は？',[hit('QX-812\nDegree of protection IP67')]).supported


def test_numbered_sound_pattern_is_not_an_alternate_model():
    assert check_evidence('QX-812のブザーパターンは？',[hit('QX-812\nNo.1 Rapid beep sound')]).supported


def test_measured_temperature_does_not_prove_operating_range():
    q='QX-812の使用周囲温度範囲は？'
    assert not check_evidence(q,[hit('QX-812 Measured at an ambient temperature of 23°C')]).supported
    assert check_evidence(q,[hit('QX-812 Operating temperature -15 to 55°C')]).supported


def test_standard_model_modifier_applies_to_its_own_comparison_subject():
    q='QX-812標準形とTR-427の出力電圧を比較'
    other=hit('TR-427 Output voltage 30V',doc='vendor-b')
    assert not check_evidence(q,[hit('QX-812 Optional model Output voltage 18V'),other]).supported
    assert check_evidence(q,[hit('QX-812 Standard model Output voltage 18V'),other]).supported


def test_contact_rating_cannot_be_replaced_by_other_voltage_rating():
    q='QX-812の接点定格は？'
    assert not check_evidence(q,[hit('QX-812 Insulation rating 2000V')]).supported
    assert check_evidence(q,[hit('QX-812 Contact rating 5A at 250V')]).supported
