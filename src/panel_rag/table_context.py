"""Recover only explicit header/group regions lost by a PDF grid extractor.

No cell values are filled. Literal words and existing ruled model columns are
required. Input/output groups additionally need full-width drawn separators.
"""
import re
from collections import defaultdict
from copy import deepcopy
from .evidence import clean


def contextualize(table):
    result=deepcopy(table)
    rows,boxes=result['rows'],result['boxes']; words=result.get('words',[]);bbox=result.get('bbox')
    for ri,row in enumerate(rows[:8]):
        models=[(c,v,b) for c,(v,b) in enumerate(zip(row,boxes[ri])) if v and b
                and re.fullmatch(r'[A-Za-z0-9]+(?:[-.][A-Za-z0-9]+)+',v.strip())
                and re.search(r'[A-Za-z]',v) and re.search(r'\d',v)]
        if len(models)<2: continue
        if any(v and clean(v) in ['model','modelnumber','型式','形名'] for v in row): continue
        top,bottom=models[0][2][1],models[0][2][3]
        if any(abs(b[1]-top)>.5 or abs(b[3]-bottom)>.5 for _,_,b in models): continue
        first=min(c for c,_,_ in models); left=min(b[0] for _,_,b in models)
        prefix=[w for w in words if w[2]<=left+.2 and w[1]>=top-.2 and w[3]<=bottom+.2
                and (not bbox or w[0]>=bbox[0]-.2)]
        label=' '.join(w[4] for w in sorted(prefix,key=lambda w:w[0]))
        if clean(label) not in ['model','modelnumber','型式','形名']: continue
        owners=[c for c,b in enumerate(boxes[ri][:first]) if b and b[1]<=top+.5 and b[3]>=bottom-.5]
        if len(owners)!=1: continue
        col=owners[0]
        rows[ri][col]=label
        boxes[ri][col]=(min(w[0] for w in prefix),top,left,bottom)
        result.setdefault('header_words',{})[ri]=[list(w[:4]) for w in prefix]
    # A border crossing the entire table separates product-property groups.
    # Short row rules do not authorize an OUTPUT/INPUT scope.
    groups=[]
    if bbox:
        def inside(w):return w[0]>=bbox[0]-.2 and w[2]<=bbox[2]+.2 and w[1]>=bbox[1]-.2 and w[3]<=bbox[3]+.2
        boundaries=sorted({(a[1]+b[1])/2 for a,b in result.get('horizontal_rules',[])
                           if min(a[0],b[0])<=bbox[0]+3 and max(a[0],b[0])>=bbox[2]-3})
        for word in words:
            if not inside(word):continue
            if clean(word[4]) not in ['input','output']: continue
            cy=(word[1]+word[3])/2
            existing=[(v,b) for row,bs in zip(rows,boxes) for v,b in zip(row,bs)
                      if v and b and clean(v)==clean(word[4]) and b[0]<=word[0] and b[2]>=word[2]
                      and b[1]<=cy<=b[3]]
            if existing: continue
            label_lefts=[b[0] for row,bs in zip(rows,boxes) for v,b in zip(row,bs)
                         if v and b and len(v)<100 and b[0]>word[2] and b[1]<=cy<=b[3]]
            if not label_lefts: continue
            left=min(label_lefts)
            above=[y for y in boundaries if y<word[1]]; below=[y for y in boundaries if y>word[3]]
            if not above or not below: continue
            top,bottom=max(above),min(below)
            others=[w for w in words if inside(w) and clean(w[4]) in ['input','output'] and w[2]<left
                    and top<(w[1]+w[3])/2<bottom]
            if len(others)!=1: continue
            groups.append(dict(text=word[4],box=(bbox[0],top,left,bottom),
                               source_cells=[list(word[:4]),[bbox[0],top,bbox[2],top],[bbox[0],bottom,bbox[2],bottom]]))
    result['recovered_groups']=groups
    return result


def note_definitions(words):
    lines=defaultdict(list)
    for w in words: lines[(w[5],w[6])].append(w)
    notes={};active=None
    def retain(item):
        if not item:return
        number,block,text,ws=item
        value=dict(text=text,bbox=[min(w[0] for w in ws),min(w[1] for w in ws),max(w[2] for w in ws),max(w[3] for w in ws)])
        # A duplicate definition is ambiguous; never choose one by proximity.
        notes[number]=None if number in notes else value
    for (block,number),line in sorted(lines.items()):
        line=sorted(line,key=lambda w:w[0]);text=' '.join(w[4] for w in line)
        match=re.match(r'^\s*(?:(?:Note\s*|注\s*)([1-9]\d?)\s*[:：.]\s*|\*([1-9]\d?)[.:：]?\s+|([1-9]\d?)\.\s+)(.+)',text,re.I)
        if match:
            retain(active);active=(match[1] or match[2] or match[3],block,text,list(line))
        elif active and active[1]==block:
            active=(active[0],block,active[2]+' '+text,active[3]+line)
        else:
            retain(active);active=None
    retain(active)
    return notes


def with_conditions(facts,words,page):
    notes=note_definitions(words)
    for fact in facts:
        conditions=list(fact['conditions']); sources=[]
        label=fact['original_label'];value=fact['original_value']
        for text in [label,value]:
            for term in re.findall(r'\(([^()]*)\)',text):
                if term.strip(): conditions.append(term.strip())
        references=set(re.findall(r'(?:Note\.?\s*|注\s*|\*)(\d{1,2})',label+' '+value,re.I))
        # Superscript markers often extract immediately after a label word.
        references.update(re.findall(r'(?<=[A-Za-z)])(\d{1,2})(?=\s*(?:\(|$))',label))
        for number in sorted(references):
            note=notes.get(number)
            if not note:
                fact.setdefault('unresolved_condition_references',[]).append(number)
                continue
            conditions.append(note['text']);sources.append(dict(page=page,**note))
            fact['source_cells'].append(note['bbox'])
        fact['conditions']=list(dict.fromkeys(conditions))
        if sources: fact['condition_sources']=sources
    return facts
