"""Bind split catalogue model codes and typed values using grid geometry.

Only explicit code headings, exact concatenation and a unique row qualify.
The original page remains unchanged. Every fact carries the source cell boxes.
"""
import re
from dataclasses import replace
from .lexical import identifiers, subjects, identifier_present, identifier_key


def row_code_facts(rows, boxes, requested):
    facts=[]
    for hi,row in enumerate(rows[:6]):
        code_columns=[]
        for col,heading in enumerate(row):
            if not heading or not re.search(r'catalog\s*code|model\s*code|型式|形名',heading,re.I): continue
            prefixes=identifiers(heading)
            if len(prefixes)==1:
                code_columns.append((col,prefixes[0],heading))
        for section,(code_col,prefix,heading) in enumerate(code_columns):
            end=code_columns[section+1][0] if section+1<len(code_columns) else len(row)
            for target in requested:
                matching=[]
                for ri,values in enumerate(rows[hi+1:],hi+1):
                    code=values[code_col]
                    if not code or not re.fullmatch(r'[A-Za-z0-9.-]{2,40}',code.strip()): continue
                    if identifier_key(prefix+code)==identifier_key(target): matching.append((ri,values,code))
                if len(matching)!=1: continue
                ri,values,code=matching[0]
                original_prefix=next((token for token in re.findall(r'[A-Za-z0-9.-]+',heading)
                                      if identifier_key(token)==identifier_key(prefix)),prefix)
                for col in range(code_col+1,end):
                    cell=boxes[ri][col]
                    value=values[col]
                    if not cell or not value or not re.fullmatch(r'\d+(?:\.\d+)*',value.strip()): continue
                    cx=(cell[0]+cell[2])/2
                    # Inherit a merged heading only when its rectangle covers
                    # this data column, not merely because the text is nearby.
                    candidates=[(j,h) for j,h in enumerate(row) if h and boxes[hi][j]
                                and boxes[hi][j][0]<=cx<=boxes[hi][j][2]]
                    if len(candidates)!=1: continue
                    if not boxes[hi][code_col] or not boxes[ri][code_col]: continue
                    header_col,label=candidates[0]
                    compact=re.sub(r'\s+','',label).lower()
                    if 'output' in compact and ('amp' in compact or 'current(a)' in compact):
                        prop,unit='output_current','A'
                    elif compact in ['frame','framesize','フレーム番号']:
                        prop,unit='frame',''
                    else: continue
                    conditions=[]
                    for qi in range(hi+1,ri):
                        qualifier=rows[qi][col]
                        if rows[qi][code_col] is None and qualifier and re.fullmatch(r'[A-Z]{1,6}',qualifier.strip()):
                            conditions.append(qualifier.strip())
                    facts.append({'model':target,'display_model':original_prefix+' '+code,
                                  'property':prop,'value':value.strip()+unit,
                                  'conditions':conditions,'original_label':label,'original_value':value,
                                  'original_code_header':heading,
                                  'prefix':prefix,'suffix':code,'row':ri,'column':col,
                                  'source_cells':[list(boxes[hi][code_col]),list(boxes[ri][code_col]),
                                                  list(boxes[hi][header_col]),list(cell)],
                                  'provenance':'unique row under explicit catalogue code header'})
    return facts


class CatalogEvidence:
    def __init__(self,path_resolver):
        self.path_resolver=path_resolver
        self.cache={}
        self.matrix_cache={}
        self.explicit_cache={}
        self.contact_cache={}

    def enrich_pages(self,question,pages):
        """Prepare document-level identity proofs once, then enrich pages."""
        from .evidence import clean
        from .matrix_binding import read_document,read_explicit_page
        models=subjects(question)
        if any(t in clean(question) for t in ['接点定格','接点仕様','contactrating']):
            from .contact_tables import read_document as contact_document
            for page in pages:
                if page.document_id in self.contact_cache or not any(identifier_present(m,page.text) for m in models): continue
                path=self.path_resolver(page.document_id)
                try:
                    self.contact_cache[page.document_id]=contact_document(path) if path else {}
                except Exception:
                    self.contact_cache[page.document_id]={}
        for page in pages:
            text=clean(page.text)
            catalogue=('modelnumber' in text or 'partnumber' in text) and 'outputvoltage' in text and 'outputcurrent' in text
            if not catalogue or not any(identifier_present(m,page.text) for m in models): continue
            if page.document_id in self.matrix_cache: continue
            path=self.path_resolver(page.document_id)
            if path is None: continue
            try:
                self.matrix_cache[page.document_id]=read_document(path)
            except Exception:
                # An unreadable or ambiguous source creates no link.
                self.matrix_cache[page.document_id]={}
        result=[]
        for page in pages:
            page=self.enrich(question,page)
            direct=[]
            if any(identifier_present(m,page.text) for m in models) and any(t in clean(page.text) for t in ['model','型式','形名']):
                key=(page.document_id,page.page_number)
                if key not in self.explicit_cache:
                    path=self.path_resolver(page.document_id)
                    try:
                        self.explicit_cache[key]=read_explicit_page(path,page.page_number) if path else []
                    except Exception:
                        self.explicit_cache[key]=[]
                direct=self.explicit_cache[key]
            facts=[f for f in self.matrix_cache.get(page.document_id,{}).get(page.page_number,[])
                   if any(identifier_key(m)==identifier_key(f['model']) for m in models)]
            facts += [f for f in direct if any(identifier_key(m)==identifier_key(f['model']) for m in models)]
            facts += [f for f in self.contact_cache.get(page.document_id,{}).get(page.page_number,[])
                      if any(identifier_key(m)==identifier_key(f['model']) for m in models)]
            if facts:
                existing=page.metadata.get('structured_facts',[])
                linked=page.metadata.get('linked_models',[])
                page=replace(page,metadata={**page.metadata,'structured_facts':existing+facts,
                    'linked_models':list(dict.fromkeys(linked+[f['model'] for f in facts])),
                    'required_source_pages':sorted({f['binding']['page'] for f in facts})})
            result.append(page)
        return result

    def enrich(self,question,page):
        wanted=[]
        for model in identifiers(question):
            parts=model.split('-')
            if len(parts)>1 and not identifier_present(model,page.text) and all(identifier_present(p,page.text) for p in parts):
                wanted.append(model)
        if not wanted: return page
        path=self.path_resolver(page.document_id)
        if path is None: return page
        key=(page.document_id,page.page_number)
        if key not in self.cache:
            import pymupdf
            try:
                with pymupdf.open(path) as pdf:
                    self.cache[key]=[(t.extract(),[r.cells for r in t.rows])
                                     for t in pdf[page.page_number-1].find_tables().tables]
            except Exception as error:
                # Parsing failure never grants a model link; keep the original
                # page and a non-sensitive diagnostic for this request.
                return replace(page,metadata={**page.metadata,'table_link_error':type(error).__name__})
        facts=[]
        for rows,boxes in self.cache[key]: facts.extend(row_code_facts(rows,boxes,wanted))
        if not facts: return page
        return replace(page,metadata={**page.metadata,'structured_facts':facts,
                       'linked_models':list(dict.fromkeys(f['model'] for f in facts))})
