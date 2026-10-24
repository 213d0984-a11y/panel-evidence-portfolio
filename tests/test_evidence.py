import pytest
from panel_rag.evidence import check_evidence
from panel_rag.models import SearchHit

def hit(text,doc='one.pdf',page=1):
    return SearchHit('test','test',doc,page,text,0.99)

@pytest.mark.parametrize('question,text',[
    ('ZX-100の通信速度は何ですか。','ZX-100 Output voltage 24 V'),
    ('ZX-100の通信速度は何ですか。','ZX-100 Communication speed: see manual. Output 24 V'),
    ('ZX-100の出力電圧は？','ZX-100 Output voltage: not specified. Weight 24 g'),
    ('ZX-100の使用周囲温度と出力電圧は？','ZX-100 Operating temperature 25°C'),
    ('ZX-999の出力電圧は？','ZX-100 Output voltage 24V'),
    ('ZX-100のZigbee通信速度は？','ZX-100 Communication speed 100Mbps'),
    ('ZX-100の光学解像度は？','ZX-100の光学関連の情報。距離 20 mm'),
    ('ZX-100の出力電圧は？','ZX-100 Input voltage 24 V'),
    ('ZX-100の入力電圧と出力電圧は？','ZX-100 Output voltage 24 V'),
])
def test_missing_direct_evidence(question,text):
    assert not check_evidence(question,[hit(text)]).supported

@pytest.mark.parametrize('question,text',[
    ('ZX-100の出力電圧は？','ZX-100 Output voltage 24 V'),
    ('ＺＸ－１００の出力電圧は？','ZX-100 Output voltage 24 V'),
    ('ZX-100の使用周囲温度は？','ZX-100 Operating temperature -20 to +50°C'),
    ('ZX-100の定格出力電流は？','ZX-100 Rated output current 2.5A'),
    ('ZX-100のZigbee通信速度は？','ZX-100 Zigbee communication speed 100Mbps'),
])
def test_direct_specification(question,text):
    assert check_evidence(question,[hit(text)]).supported

def test_no_cross_document_evidence_borrowing():
    hits=[hit('ZX-100 Output voltage 24 V'),hit('ZX-200 Zigbee communication speed 100Mbps','two.pdf')]
    assert not check_evidence('ZX-100のZigbee通信速度は？',hits).supported

def test_cited_page_must_support_question():
    hits=[hit('ZX-100 Product outline'),hit('ZX-100 Output voltage 24 V',page=2)]
    assert check_evidence('ZX-100の出力電圧は？',hits).supported
    assert not check_evidence('ZX-100の出力電圧は？',hits,{('one.pdf',1)}).supported

def test_repeated_heading_does_not_hide_specification():
    text = 'ZX-100 Terminal screw material: steel. ' + 'Housing material: plastic. ' * 20
    text += ' Terminal screw M4'
    assert check_evidence('ZX-100の端子ねじは？',[hit(text)]).supported

def test_alpha_only_series_must_also_have_evidence():
    assert not check_evidence('ABC-GSとZX-100の出力電圧を比較',[hit('ZX-100 Output voltage 24 V')]).supported
