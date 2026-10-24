"""Audit immutable inputs and aggregate regressions without manufacturer prose."""
import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def read(path):return json.loads(path.read_text(encoding='utf-8'))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--audit-dir',type=Path,required=True)
    audit=parser.parse_args().audit_dir
    frozen=read(ROOT/'eval/audit-input-hashes.json')
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==digest for p,digest in frozen.items())
    assert (ROOT/'benchmarks/hdr60.json').read_bytes()==(audit/'hdr60-frozen-questions.json').read_bytes()
    reports={n:read(ROOT/f'eval/{n}-final-results.json') for n in ['fixed28','hdr60','ndr','puls','relay','cosel','phoenix']}
    current_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'src/panel_rag').glob('*.py')}
    assert all(r['code_sha256']==current_hashes for r in reports.values())
    before=read(audit/'fixed28-independent.json');after=reports['fixed28']
    assert before['dataset_sha256']==after['dataset_sha256']==hashlib.sha256((ROOT/'benchmarks/fixed28.json').read_bytes()).hexdigest()
    stable=['embedding_model','min_relevance_score','top_k','chunk_size','chunk_overlap','llm_provider','llm_model']
    assert all(before['settings'][key]==after['settings'][key] for key in stable)
    prior={r['question_id']:r for r in before['results']}
    worsened=[r['question_id'] for r in after['results'] if prior[r['question_id']]['strict_pass'] and not r['strict_pass']]
    assert not worsened
    c06=next(r for r in after['results'] if r['question_id']=='C-06')
    bound=[f for c in c06['response']['citations'] for f in c['hit']['metadata'].get('structured_facts',[])
           if f['model']=='PS5R-VB24' and f['property']=='temperature']
    assert any('75' in f['value'] and any('Note 4' in c and 'derating' in c for c in f['conditions']) for f in bound)
    suites=ET.parse(ROOT/'eval/local-audit-tests.xml').getroot().findall('testsuite')
    tests={key:sum(int(s.attrib[key]) for s in suites) for key in ['tests','failures','errors','skipped']}
    assert tests==dict(tests=164,failures=0,errors=0,skipped=0)
    ui=read(ROOT/'eval/ui-audit.json');assert ui['power_direct'] and ui['temperature_conditions_visible'] and ui['unknown_model_refused']
    summary=dict(version='0.5.1',baseline_commit='d6de6a46751a18d5538268234cc66bea27efaf26',tests=tests,
                 fixed28_before=before['summary'],fixed28_after=after['summary'],fixed28_worsened=worsened,
                 hdr60_first_pass=read(audit/'hdr60-first-pass.json')['summary'],hdr60_initial_direct_answers='0/6, independently audited',
                 regressions={n:r['summary'] for n,r in reports.items() if n!='fixed28'},
                 self_authored_8=read(ROOT/'data/sample-regression/report.json')['summary'],
                 audit_inputs_unchanged=True,settings_unchanged={k:after['settings'][k] for k in stable},
                 core_sha256=current_hashes,ui_sha256=hashlib.sha256((ROOT/'streamlit_app.py').read_bytes()).hexdigest(),
                 semantic_note='Presentation coverage is not numeric correctness. HDR-60 page 2 and PS5R-VB24 page 2 were separately reviewed against rendered originals; frozen 70C reference was not changed.',
                 limitations=['HDR-60 is now regression material, not a new blind result.','Fixed positives have complete bound-value presentation for 3/23; other page excerpts are not direct numeric-answer successes.',
                              'No live external LLM, new API key, paid service, GitHub publication or clean-PC test.'])
    (ROOT/'eval/local-audit-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    (ROOT/'docs/portfolio/audit-v051-metrics.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    metrics=read(ROOT/'docs/portfolio/metrics.json')
    metrics['fixed_28']=after['summary'];metrics['HDR60_first_pass_8']=summary['hdr60_first_pass']
    metrics['v051_regressions']=summary['regressions'];metrics['v051_note']=summary['limitations']
    (ROOT/'docs/portfolio/metrics.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:summary[k] for k in ['version','tests','fixed28_worsened','audit_inputs_unchanged']},ensure_ascii=False))

if __name__=='__main__':main()
