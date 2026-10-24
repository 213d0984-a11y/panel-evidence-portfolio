"""Local regression replay; no input edits, downloads, keys or publication."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
import evaluate_benchmark as benchmark

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-root',type=Path,required=True)
    parser.add_argument('--audit-dir',type=Path,required=True)
    args=parser.parse_args();r=args.reference_root;a=args.audit_dir
    inputs=[p for p in a.iterdir() if p.is_file() and p.suffix in ['.json','.pdf','.xml']]
    inputs += list((a/'original-pages').glob('*.png'))
    frozen={str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    assert (ROOT/'benchmarks/hdr60.json').read_bytes()==(a/'hdr60-frozen-questions.json').read_bytes()
    (ROOT/'eval').mkdir(exist_ok=True)
    snapshot=ROOT/'eval/audit-input-hashes.json'
    if snapshot.exists(): assert json.loads(snapshot.read_text(encoding='utf-8'))==frozen
    else:snapshot.write_text(json.dumps(frozen,ensure_ascii=False,indent=2),encoding='utf-8')
    cases=[('fixed28','fixed28',r/'data/documents/real_world'),('hdr60','hdr60',a),
           ('ndr','blind',r/'data/documents/holdout'),('puls','holdout',r/'data/documents/holdout'),
           ('relay','relay',r/'data/holdout-sensor'),('cosel','cosel',r/'data/documents/unseen'),
           ('phoenix','phoenix',r/'data/documents/unseen')]
    for name,dataset,documents in cases:
        print('FINAL',name,flush=True)
        sys.argv=['evaluate_benchmark.py','--dataset',str(ROOT/f'benchmarks/{dataset}.json'),
                  '--documents',str(documents),'--storage',str(ROOT/f'data/{name}-regression'),
                  '--output',str(ROOT/f'eval/{name}-final-results.json'),'--reuse-index']
        benchmark.main()
    assert frozen=={str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    print('Audit inputs unchanged; final core hashes recorded per dataset.',flush=True)

if __name__=='__main__':main()
