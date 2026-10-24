"""Contact ratings with explicit pole/load header paths and identity proofs.

Model names are never decoded. A row-oriented rating table is linked only by
an explicitly declared construction group AND pole count in the same PDF.
"""
import re
from collections import defaultdict
from .evidence import clean
from .lexical import identifier_key,identifier_present


def cells(table):
    for ri,row in enumerate(table['rows']):
        for ci,value in enumerate(row):
            box=table['boxes'][ri][ci]
            if value and box: yield ri,ci,value,box


def above(table,box,predicate):
    cx=(box[0]+box[2])/2
    return [(r,c,v,b) for r,c,v,b in cells(table)
            if b[0]<=cx<=b[2] and b[3]<=box[1]+.5 and predicate(clean(v))]


def beside(table,box,before,predicate):
    cy=(box[1]+box[3])/2
    return [(r,c,v,b) for r,c,v,b in cells(table)
            if c<before and b[1]<=cy<=b[3] and predicate(clean(v))]


def model_profiles(table,page):
    """Literal model columns under a physical '<construction> Models' header."""
    result=[]
    entries=list(cells(table))
    for ri,row in enumerate(table['rows'][:8]):
        candidates=[(ci,v,table['boxes'][ri][ci]) for ci,v in enumerate(row)
                    if v and table['boxes'][ri][ci]
                    and re.fullmatch(r'[A-Za-z]+[A-Za-z0-9]*(?:[-.][A-Za-z0-9]+)*',v)
                    and re.search(r'\d',v)]
        if len(candidates)<2: continue
        for col,model,box in candidates:
            # A similarly named high-capacity/option column makes the bare
            # model ambiguous; don't silently assume a default version.
            occurrences=[v for r,c,v,b in entries if r<8 and identifier_present(model,v)]
            if len(occurrences)!=1: continue
            groups=above(table,box,lambda v: bool(re.fullmatch(r'[a-z]+models',v)))
            if len(groups)!=1: continue
            labels=[(r,c,v,b) for r,c,v,b in entries
                    if clean(v) in ['no.ofpoles','noofpoles','numberofpoles','極数'] and c<col]
            values=[]
            cx=(box[0]+box[2])/2
            for lr,lc,label,lb in labels:
                for r,c,v,b in entries:
                    if r==lr and c>lc and re.fullmatch(r'\d{1,2}',v.strip()) and b[0]<=cx<=b[2]:
                        values.append((v,lb,b))
            if len(values)!=1: continue
            poles,label_box,value_box=values[0]
            group=groups[0]
            result.append(dict(model=model,category=group[2],poles=poles,page=page,
                               source_cells=[list(box),list(group[3]),list(label_box),list(value_box)],
                               anchor_text=[group[2],'No. of poles',poles]))
    return result


def rated_rows(table,page):
    """Bind current/voltage only under the same explicit Rated Load parent."""
    rows=[]
    for ri,col,value,box in cells(table):
        if not re.fullmatch(r'\d+(?:\.\d+)?a',clean(value)): continue
        parents=above(table,box,lambda v:v=='ratedload')
        loads=above(table,box,lambda v:v.startswith(('resistiveload','inductiveload')))
        if len(parents)!=1 or len(loads)!=1: continue
        parent=parents[0]; load=loads[0]
        # This excludes similarly named Allowable Contact Power columns.
        if not (parent[3][0]<=load[3][0] and load[3][2]<=parent[3][2]): continue
        categories=beside(table,box,col,lambda v:bool(re.fullmatch(r'[a-z]+models',v)))
        poles=beside(table,box,col,lambda v:bool(re.fullmatch(r'\d+poles?',v)))
        contacts=beside(table,box,col,lambda v:v in ['no','nc'])
        if len(categories)!=1 or len(poles)!=1 or len(contacts)!=1: continue
        voltages=[]
        for vr,vc,v,vb in cells(table):
            if vr!=ri or not re.fullmatch(r'(?:ac|dc)?\d+(?:\.\d+)?v(?:ac|dc)?',clean(v)): continue
            voltage_headers=above(table,vb,lambda text:text=='voltage')
            if len(voltage_headers)!=1: continue
            vh=voltage_headers[0]
            if parent[3][0]<=vh[3][0] and vh[3][2]<=parent[3][2]: voltages.append((v,vb,vh))
        if len(voltages)!=1: continue
        voltage,vb,vh=voltages[0]
        rows.append(dict(category=categories[0][2],poles=re.search(r'\d+',poles[0][2])[0],
                         contact=contacts[0][2],load=load[2],page=page,row=ri,column=col,
                         value=value+' at '+voltage,original_value=value,original_voltage=voltage,
                         original_label=parent[2]+' / '+load[2]+' / '+vh[2],
                         source_cells=[list(b) for b in [parent[3],load[3],box,vb,vh[3],
                                        categories[0][3],poles[0][3],contacts[0][3]]]))
    return rows


def column_ratings(table,series,page):
    """Read nested pole/load columns under a literal family page heading."""
    if not series: return []
    model,heading_box=series
    entries=list(cells(table)); result=[]
    rated=[(r,c,v,b) for r,c,v,b in entries if clean(v)=='ratedload']
    if len(rated)!=1: return []
    ri,label_col,label,label_box=rated[0]
    for r,col,value,box in entries:
        if r!=ri or col<=label_col: continue
        lines=value.splitlines()
        if not lines or not all(re.fullmatch(r'\d+(?:\.\d+)?aat\d+(?:\.\d+)?v(?:ac|dc)',clean(line)) for line in lines): continue
        poles=above(table,box,lambda v:bool(re.fullmatch(r'\d+poles?',v)))
        loads=above(table,box,lambda v:v.startswith(('resistiveload','inductiveload')))
        if len(poles)!=1 or len(loads)!=1: continue
        conditions=[poles[0][2],loads[0][2]]
        source=[list(heading_box),list(label_box),list(box),list(poles[0][3]),list(loads[0][3])]
        # Two columns can have the same load name but different endurance.
        # Keep each column's explicit context rather than choosing the largest.
        cx=(box[0]+box[2])/2
        for qr,qc,qv,qb in entries:
            if qc!=label_col or not clean(qv).startswith('electricalendurance'): continue
            owners=[(v,b) for rr,cc,v,b in entries if rr==qr and cc>qc and b[0]<=cx<=b[2]]
            if len(owners)==1:
                conditions.append(qv+': '+owners[0][0]); source.extend([list(qb),list(owners[0][1])])
        result.append(dict(model=model,display_model=model,property='rating',value=value,
                           original_label=label,original_value=value,conditions=conditions,row=r,column=col,
                           source_cells=source,provenance='literal family heading and nested pole/load column headers',
                           binding=dict(page=page,model=model,series=model,
                             method='nested contact rating columns',summary='極数・負荷条件を持つ同一表の列',
                             source_cells=[list(heading_box)],anchor_text=conditions,matrix_cells=source)))
    return result


def link_ratings(profiles,rows):
    by_key=defaultdict(list); by_model=defaultdict(list)
    for profile in profiles:
        by_key[(clean(profile['category']),profile['poles'])].append(profile)
        by_model[identifier_key(profile['model'])].append(profile)
    # More than one rating table in the same document scope is ambiguous.
    table_pages=defaultdict(set)
    for row in rows: table_pages[(clean(row['category']),row['poles'])].add(row['page'])
    result=defaultdict(list)
    for row in rows:
        key=(clean(row['category']),row['poles'])
        if len(by_key[key])!=1 or len(table_pages[key])!=1: continue
        identity=by_key[key][0]
        if len(by_model[identifier_key(identity['model'])])!=1: continue
        model=identity['model']
        result[row['page']].append(dict(model=model,display_model=model,property='rating',
            value=row['value'],original_label=row['original_label'],original_value=row['original_value'],
            original_voltage=row['original_voltage'],conditions=[row['category'],row['poles']+' poles',row['contact'],row['load'],row['original_voltage']],
            row=row['row'],column=row['column'],source_cells=row['source_cells'],
            provenance='unique construction group and explicit pole count in same document',
            binding=dict(page=identity['page'],model=model,series=row['category'],
                method='construction and pole-count identity join',summary='取付形式と明示された極数の一意な対応',
                source_cells=identity['source_cells'],anchor_text=identity['anchor_text'],matrix_cells=row['source_cells'])))
    return dict(result)


def read_document(pdf_path):
    import pymupdf
    profiles=[]; row_facts=[]; result=defaultdict(list)
    with pymupdf.open(pdf_path) as pdf:
        for number,page in enumerate(pdf,1):
            text=clean(page.get_text())
            if not any(term in text for term in ['ratedload','no.ofpoles','noofpoles','numberofpoles']): continue
            headings=[(w[4],w[:4]) for w in page.get_text('words') if w[3]<page.rect.height*.10
                      and re.fullmatch(r'[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+',w[4])]
            series=headings[0] if headings and len({identifier_key(h[0]) for h in headings})==1 else None
            for source in page.find_tables().tables:
                table=dict(rows=source.extract(),boxes=[r.cells for r in source.rows])
                profiles.extend(model_profiles(table,number))
                row_facts.extend(rated_rows(table,number))
                result[number].extend(column_ratings(table,series,number))
    for page,facts in link_ratings(profiles,row_facts).items(): result[page].extend(facts)
    return {page:facts for page,facts in result.items() if facts}
