"""Recover complete page evidence and cover requested subjects, without gold data.

The local store already scores the complete corpus. Reuse that candidate pool;
do not re-embed, read unregistered PDFs, or use filenames as relevance signals.
"""
from collections import defaultdict
from dataclasses import replace
import re
from .evidence import check_evidence


def merge_page(chunks):
    """Undo overlapping windows, retaining original source order and text."""
    def order(hit):
        match = re.search(r':chunk-(\d+)$', hit.chunk_id)
        return int(match[1]) if match else 0
    chunks = sorted(chunks, key=order)
    text = ''
    for chunk in chunks:
        tail = chunk.text
        overlap = next((n for n in range(min(len(text), len(tail)), min(16, len(tail))-1, -1)
                        if text.endswith(tail[:n])), 0)
        text += ('' if overlap or not text else '\n') + tail[overlap:]
    best = max(chunks, key=lambda h:h.score)
    return replace(best, chunk_id=f'{best.document_id}:page-{best.page_number}',
                   text=text, metadata={**best.metadata,
                       'evidence_unit': 'page', 'source_chunk_ids': [c.chunk_id for c in chunks]})


def evidence_pages(question, candidates, limit, min_score, page_enricher=None):
    groups = defaultdict(list)
    for hit in candidates:
        groups[(hit.document_id, hit.page_number)].append(hit)
    # Dictionary insertion order preserves the first hybrid rank on score ties.
    pages = [merge_page(chunks) for chunks in groups.values()]
    if page_enricher:
        pages=page_enricher(question,pages)
    by_key={(p.document_id,p.page_number):i for i,p in enumerate(pages)}
    bundles=[]
    for i,page in enumerate(pages):
        dependencies=[(page.document_id,n) for n in page.metadata.get('required_source_pages',[])]
        if any(key not in by_key for key in dependencies):
            bundles.append(None)
        else:
            bundles.append(list(dict.fromkeys([i]+[by_key[key] for key in dependencies])))
    checks=[]
    for i,page in enumerate(pages):
        bundle=bundles[i]
        if bundle is None or page.score<min_score:
            checks.append(None); continue
        evidence=[page]+[replace(pages[j],metadata={**pages[j].metadata,'binding_proof_only':True})
                         for j in bundle if j!=i]
        checks.append(check_evidence(question,evidence))
    coverage = [{(d['model'], p) for d in check.details for p in d['found']
                 if not d['missing_qualifiers']} if check else set() for check in checks]
    subjects=[{d['model'] for d in check.details if d['model'] is not None} if check else set() for check in checks]
    selected, primary, covered, seen_subjects = [], set(), set(), set()
    remaining = list(range(len(pages)))
    while remaining and len(selected) < limit:
        possible=[i for i in remaining if bundles[i] is not None
                  and len(set(selected)|set(bundles[i]))<=limit]
        if not possible: break
        # A rejected specification must not erase the requested product from
        # search results. Subject coverage breaks ties only AFTER field gain;
        # it never authorizes an answer or replaces sufficient field evidence.
        index = max(possible, key=lambda i:(len(coverage[i] - covered),len(subjects[i]-seen_subjects),len(coverage[i])))
        if coverage[index]-covered or index not in selected: primary.add(index)
        selected.extend(j for j in bundles[index] if j not in selected)
        covered.update(coverage[index])
        seen_subjects.update(subjects[index])
        remaining.remove(index)
    return [pages[i] if i in primary else replace(pages[i],metadata={**pages[i].metadata,'binding_proof_only':True})
            for i in selected]
