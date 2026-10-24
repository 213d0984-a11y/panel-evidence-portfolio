"""Portable evaluation with frozen authored questions and separately supplied PDFs.

No paid API, downloads, manufacturer-specific code or changes to RAG defaults.
Run from a source checkout after installing the project.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
from dataclasses import asdict


def grade(case,answer):
    docs=case['expected_document']
    row={'question_id':case['question_id'],'category':case['category'],
         'expected_answerable':case['expected_answerable'],'actual_answerable':answer.answerable,
         'answerability_correct':case['expected_answerable']==answer.answerable,
         'refused':not answer.answerable}
    for key,hits,pages in [('document_retrieval_recall',answer.retrieved_hits,False),
                           ('page_retrieval_recall',answer.retrieved_hits,True),
                           ('citation_recall',[c.hit for c in answer.citations],False),
                           ('citation_page_recall',[c.hit for c in answer.citations],True)]:
        row[key]=sum(any(h.file_name==d and (not pages or h.page_number in case['expected_page'][d])
                         for h in hits) for d in docs)/len(docs) if docs else None
    row['strict_pass']=row['answerability_correct'] and (not docs or all(row[k]==1 for k in
        ['document_retrieval_recall','page_retrieval_recall','citation_recall','citation_page_recall']))
    return row


def presentation(answer,check):
    """Do not count finding numbers inside a whole-page excerpt as extraction.

    Coverage describes the presentation path, NOT numeric correctness. Values
    and their conditions still need separate comparison to the original PDF.
    """
    from panel_rag.lexical import identifier_key
    required={(identifier_key(d['model']),prop) for d in check.details if d.get('model')
              for prop in d['found']} if check else set()
    supplied={(identifier_key(f['model']),f['property']) for c in answer.citations
              for f in c.hit.metadata.get('structured_facts',[])}
    complete=bool(answer.answerable and required and required<=supplied)
    return dict(answer_presentation='refused' if not answer.answerable else 'bound_model_values' if complete else 'page_excerpt_or_mixed',
                complete_bound_value_presentation=complete)


def summarize(rows):
    def mean(key,selected):
        values=[r[key] for r in selected if r.get(key) is not None]
        return sum(values)/len(values) if values else None
    pos=[r for r in rows if r['expected_answerable']]
    neg=[r for r in rows if not r['expected_answerable']]
    return dict(cases=len(rows),answerability_accuracy=mean('answerability_correct',rows),
                strict_pass_rate=mean('strict_pass',rows),
                document_retrieval_recall=mean('document_retrieval_recall',pos),
                page_retrieval_recall=mean('page_retrieval_recall',pos),
                citation_recall=mean('citation_recall',pos),
                citation_page_recall=mean('citation_page_recall',pos),
                unanswerable_refusal_rate=mean('refused',neg),
                answerable_false_refusal_rate=mean('refused',pos),
                complete_bound_value_presentation_rate=mean('complete_bound_value_presentation',pos))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,required=True)
    parser.add_argument('--documents',type=Path,required=True)
    parser.add_argument('--storage',type=Path,required=True,help='Dedicated empty index directory')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--reuse-index',action='store_true',help='Recheck an index only if registered source hashes/names match exactly')
    args=parser.parse_args()
    populated=args.storage.exists() and any(args.storage.iterdir())
    if populated and not args.reuse_index: parser.error('--storage must be empty; existing data is never deleted')
    if args.reuse_index and not populated: parser.error('--reuse-index requires an existing index')
    frozen=hashlib.sha256(args.dataset.read_bytes()).hexdigest()
    dataset=json.loads(args.dataset.read_text(encoding='utf-8'))
    paths=[]
    for source in dataset['sources']:
        name=source['file_name']
        if Path(name).name!=name or not name.endswith('.pdf'): parser.error('invalid source filename')
        path=args.documents/name
        if not path.is_file(): parser.error(f'Missing independently obtained source: {name}')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=source['sha256']:
            parser.error(f'Source revision mismatch: {name}; do not silently score a different revision')
        paths.append(path)
    os.environ['RAG_DATA_DIR']=str(args.storage.resolve())
    os.environ['RAG_LLM_PROVIDER']='extractive'
    from panel_rag.bootstrap import build_service
    service,settings=build_service(Path.cwd())
    try:
        if args.reuse_index:
            expected={(s['file_name'],s['sha256']) for s in dataset['sources']}
            registered={(r.file_name,r.sha256) for r in service.list_documents()}
            if registered!=expected: parser.error('Registered sources do not match the frozen dataset')
        else:
            for path in paths: service.ingest_pdf(path.name,path.read_bytes())
        rows=[]
        for case in dataset['questions']:
            answer=service.ask(case['question'])
            rows.append({**grade(case,answer),'response':asdict(answer),
                         **presentation(answer,service.last_citation_check),
                         'evidence_check':asdict(service.last_evidence_check) if service.last_evidence_check else None})
            print(case['question_id'],answer.answerable,flush=True)
        assert frozen==hashlib.sha256(args.dataset.read_bytes()).hexdigest()
        report={'dataset_sha256':frozen,'summary':summarize(rows),'results':rows,
                'index_mode':'verified existing source hashes' if args.reuse_index else 'fresh index',
                'settings':{k:str(v) if isinstance(v,Path) else v for k,v in asdict(settings).items()},
                'metric_note':'Strict pass measures answerability/source/page agreement. Bound-value presentation measures typed model/property coverage, not correctness of all values/conditions. Whole-page excerpts do not count as direct value answers.',
                'code_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in Path('src/panel_rag').glob('*.py')}}
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report['summary'],indent=2))
    finally: service.vector_store.close()

if __name__=='__main__': main()
