"""Join a product list to a specification matrix using explicit source facts.

A repeated page heading, output voltage AND rated output current must identify
one catalogue row and one matrix column in the same registered document.
Ambiguous keys are rejected. No model decoding, nearest-page or filename rules.
"""
import re
from collections import defaultdict
from decimal import Decimal
from .evidence import clean
from .lexical import identifier_key


def quantity(value, kind, label=''):
    """A single explicit quantity, not a range, typical value or inferred code."""
    units=r'(?:mv|v)(?:dc|ac)?' if kind=='voltage' else r'(?:ma|a)'
    match=re.fullmatch(r'([0-9]+(?:\.[0-9]+)?)('+units+')',clean(value or ''))
    if not match: return None
    number,unit=Decimal(match[1]),match[2]
    if unit.startswith('m'): number/=1000; unit=unit[1:]
    if kind=='voltage' and unit=='v':
        if 'vdc' in clean(label): unit='vdc'
        elif 'vac' in clean(label): unit='vac'
    return str(number.normalize()),unit


def _row_text(words,box):
    # Project a missing model cell only from an explicit column header and
    # two aligned, drawn data cells. Never propagate a neighbouring model.
    selected=[w for w in words if w[0]>=box[0]-.2 and w[2]<=box[2]+.2
              and w[1]>=box[1]-.2 and w[3]<=box[3]+.2]
    return ' '.join(w[4] for w in sorted(selected,key=lambda w:(w[1],w[0])))


def catalogue_identities(table,series,page):
    rows,boxes=table['rows'],table['boxes']
    result=[]
    for hi,header in enumerate(rows[:6]):
        def column(pattern):
            found=[i for i,v in enumerate(header) if v and re.fullmatch(pattern,clean(v))]
            return found[0] if len(found)==1 else None
        model_col=column(r'(?:modelnumber|partnumber|型式|形名)')
        voltage_col=column(r'outputvoltage(?:\(v(?:dc|ac)?\))?')
        current_col=column(r'(?:rated)?outputcurrent(?:\(a\))?')
        if None in (model_col,voltage_col,current_col): continue
        for ri,row in enumerate(rows[hi+1:],hi+1):
            if len(row)!=len(header): continue
            vb,cb=boxes[ri][voltage_col],boxes[ri][current_col]
            if not vb or not cb or abs(vb[1]-cb[1])>.5 or abs(vb[3]-cb[3])>.5: continue
            voltage=quantity(row[voltage_col],'voltage',header[voltage_col])
            current=quantity(row[current_col],'current',header[current_col])
            if not voltage or not current: continue
            model_box=boxes[ri][model_col]
            model=row[model_col]
            if model_box is None:
                mh=boxes[hi][model_col]
                if not mh: continue
                model_box=(mh[0],vb[1],mh[2],vb[3])
                model=_row_text(table.get('words',[]),model_box)
            if not model or not re.fullmatch(r'[A-Za-z0-9]+(?:[-.][A-Za-z0-9]+)*',model.strip()): continue
            if not (re.search(r'[A-Za-z]',model) and re.search(r'\d',model)): continue
            result.append(dict(model=model.strip(),series=series,page=page,voltage=voltage,current=current,
                               source_cells=[list(model_box),list(vb),list(cb)],
                               anchor_text=[header[voltage_col],row[voltage_col],header[current_col],row[current_col]]))
    return result


def matrix_columns(table,series,page):
    rows,boxes=table['rows'],table['boxes']
    result=[]
    voltage_rows=[(ri,ci,value) for ri,row in enumerate(rows[:8]) for ci,value in enumerate(row)
                  if value and clean(value) in ['outputvoltage(vdc)','outputvoltage(vac)','outputvoltage']]
    current_rows=[(ri,ci,value) for ri,row in enumerate(rows) for ci,value in enumerate(row)
                  if value and clean(value) in ['ratedoutputcurrent','ratedoutputcurrent(a)']]
    if len(voltage_rows)!=1 or len(current_rows)!=1: return []
    vi,vl,vlabel=voltage_rows[0]
    ai,al,alabel=current_rows[0]
    if ai<=vi: return []
    for col in range(max(vl,al)+1,len(rows[vi])):
        voltage=quantity(rows[vi][col],'voltage',vlabel)
        current=quantity(rows[ai][col],'current',alabel)
        vb,ab=boxes[vi][col],boxes[ai][col]
        if not voltage or not current or not vb or not ab: continue
        if abs(vb[0]-ab[0])>1 or abs(vb[2]-ab[2])>1: continue
        result.append(dict(series=series,page=page,voltage=voltage,current=current,
                           column=col,data_start=max(vl,al)+1,source_cells=[list(vb),list(ab)],table=table))
    return result


def _property(label,group):
    value=clean(label)
    if value.startswith('voltagerange') and clean(group)=='input': return 'input_voltage'
    if value.startswith(('ratedinputvoltage','入力電圧')): return 'input_voltage'
    if value.startswith(('ambientoperatingtemperature','operatingtemperature','使用周囲温度')): return 'temperature'
    if value.startswith(('ambientoperatinghumidity','operatinghumidity','使用周囲湿度')): return 'humidity'
    if value in ['degreeofprotection','protectioncategory','environmentalprotection']: return 'protection'
    if value.startswith('ratedoutputcurrent'): return 'output_current'
    if value.startswith('boostcurrent'): return 'boost'
    if clean(group)=='output':
        if value in ['ratedcurrent','定格電流']: return 'output_current'
        if value in ['ratedpower','ratedoutputpower','定格出力電力']: return 'power'
        if value in ['dcvoltage','outputvoltage']: return 'output_voltage'
        if value in ['voltageadj.range','voltageadjustmentrange','outputvoltageadjustmentrange']: return 'output_voltage_adjustment'
    if value.startswith(('workingtemp.','workingtemperature')): return 'temperature'
    return None


def bound_properties(identity,column):
    """Read only a physical value cell covering the proven matrix column."""
    table=column['table']; rows,boxes=table['rows'],table['boxes']
    col=column['column']; header_box=column['source_cells'][0]
    cx=(header_box[0]+header_box[2])/2
    facts=[]
    for ri,row in enumerate(rows):
        labels=[(ci,v) for ci,v in enumerate(row[:column['data_start']]) if v and boxes[ri][ci]]
        if not labels: continue
        # A vertical group cell (e.g. Input) may explicitly cover several rows.
        reference=boxes[ri][labels[-1][0]]
        cy=(reference[1]+reference[3])/2
        groups=[v for qi,values in enumerate(rows) for ci,v in enumerate(values[:1])
                if v and boxes[qi][ci] and boxes[qi][ci][1]<=cy<=boxes[qi][ci][3]]
        groups += [g['text'] for g in table.get('recovered_groups',[]) if g['box'][1]<=cy<=g['box'][3]]
        group=groups[0] if len(groups)==1 else ''
        label_col,label=labels[-1]
        prop=_property(label,group)
        if not prop: continue
        cells=[(ci,v,b) for ci,(v,b) in enumerate(zip(row,boxes[ri]))
               if ci>=column['data_start'] and v and b and b[0]<=cx<=b[2]
               and b[1]<=cy<=b[3]]
        if len(cells)!=1: continue
        value_col,value,value_box=cells[0]
        if re.search(r'not specified|not available|see manual|未記載|記載なし',value,re.I): continue
        group_proof=[cell for g in table.get('recovered_groups',[]) if g['text'] in groups
                     and g['box'][1]<=cy<=g['box'][3] for cell in g['source_cells']]
        facts.append(dict(model=identity['model'],display_model=identity['model'],property=prop,value=value,
                          conditions=[],original_label=label,original_value=value,row=ri,column=value_col,
                          source_cells=[list(boxes[ri][label_col]),list(value_box)]+group_proof,
                          provenance=identity.get('method','unique catalogue row and matrix column; same heading, voltage and current'),
                          binding={'page':identity['page'],'model':identity['model'],'series':identity['series'],
                                   'method':identity.get('method','two-anchor catalogue join'),
                                   'source_cells':identity['source_cells'],
                                   'anchor_text':identity['anchor_text'],'matrix_cells':column['source_cells']}))
    return facts


def explicit_model_facts(table,page):
    """A literal model header binds a column without a cross-page join.

    Multiple header rows may list different voltage variants in one column.
    A common value is used only when a drawn cell spans the target column.
    """
    rows,boxes=table['rows'],table['boxes']
    model_headers=[(ri,ci,boxes[ri][ci]) for ri,row in enumerate(rows[:8]) for ci,v in enumerate(row)
                   if v and clean(v) in ['model','modelnumber','型式','形名'] and boxes[ri][ci]]
    targets=defaultdict(list)
    for ri,row in enumerate(rows[:8]):
        models=[(ci,v) for ci,v in enumerate(row) if v and re.fullmatch(r'[A-Za-z0-9]+(?:[-.][A-Za-z0-9]+)+',v.strip())
                and re.search(r'[A-Za-z]',v) and re.search(r'\d',v) and boxes[ri][ci]]
        if len(models)<2: continue
        for col,model in models:
            box=boxes[ri][col]; cy=(box[1]+box[3])/2
            headers=[(hi,hc,hb) for hi,hc,hb in model_headers if hi<=ri and hc<col and hb[1]<=cy<=hb[3]]
            if len(headers)!=1: continue
            hi,hc,hb=headers[0]
            identity=dict(model=model,series='',page=page,source_cells=[list(hb),list(box)],
                          anchor_text=[rows[hi][hc],model],method='explicit model column with physical value-cell coverage')
            identity['source_cells']+=table.get('header_words',{}).get(hi,[])
            column=dict(table=table,column=col,data_start=min(c for c,_ in models),source_cells=[list(box)])
            targets[identifier_key(model)].append((identity,column))
    result=[]
    for candidates in targets.values():
        if len(candidates)!=1: continue
        result.extend(bound_properties(*candidates[0]))
    return result


def read_explicit_page(pdf_path,page_number):
    import pymupdf
    from .table_context import contextualize,with_conditions
    with pymupdf.open(pdf_path) as pdf:
        page=pdf[page_number-1]
        result=[]
        words=page.get_text('words')
        rules=[(tuple(item[1]),tuple(item[2])) for drawing in page.get_drawings() for item in drawing['items']
               if item[0]=='l' and abs(item[1].y-item[2].y)<.5]
        for t in page.find_tables().tables:
            table=contextualize(dict(rows=t.extract(),boxes=[r.cells for r in t.rows],words=words,
                                     bbox=t.bbox,horizontal_rules=rules))
            result.extend(explicit_model_facts(table,page_number))
            result.extend(projected_model_facts(table,page_number))
        result=with_conditions(result,words,page_number)
        unique={}
        for f in result:
            key=(f['model'],f['property'],f['value'],tuple(f['conditions']))
            unique.setdefault(key,f)
        return list(unique.values())


def projected_model_facts(table,page):
    """Recover a simple row label from words when the parser merges labels.

    The *drawn value cell* defines the vertical band; the literal MODEL row
    defines the horizontal column. No nearest-word, blank filling, model-code
    decoding or free-form table interpretation. Repeated headers define new
    sections, and conflicting results are rejected by the evidence gate.
    """
    rows,boxes=table['rows'],table['boxes']; headers=[];result=[]
    for ri,row in enumerate(rows):
        labels=[(c,v) for c,v in enumerate(row) if v and clean(v) in ['model','modelnumber','型式','形名'] and boxes[ri][c]]
        if len(labels)!=1: continue
        lc,label=labels[0]
        models=[(c,v,b) for c,(v,b) in enumerate(zip(row,boxes[ri])) if c>lc and v and b
                and re.fullmatch(r'[A-Za-z0-9]+(?:[-.][A-Za-z0-9]+)+',v.strip())
                and re.search(r'[A-Za-z]',v) and re.search(r'\d',v)]
        if len(models)>1: headers.append((ri,lc,label,models))
    for index,(hi,lc,header,models) in enumerate(headers):
        end=headers[index+1][0] if index+1<len(headers) else len(rows)
        start=min(c for c,_,_ in models); left=min(b[0] for _,_,b in models)
        label_left=min(b[0] for b in boxes[hi][:start] if b)
        for ri in range(hi+1,end):
            for col,model,mb in models:
                cx=(mb[0]+mb[2])/2
                owners=[(ci,v,b) for ci,(v,b) in enumerate(zip(rows[ri],boxes[ri]))
                        if ci>=start and v and b and b[0]<=cx<=b[2]]
                if len(owners)!=1: continue
                ci,value,vb=owners[0]; cy=(vb[1]+vb[3])/2
                words=[w for w in table.get('words',[]) if w[0]>=label_left-.2 and w[2]<=left+.2
                       and vb[1]<(w[1]+w[3])/2<vb[3]]
                # Exclude the group column: it has its own explicit rectangle.
                groups=[(v,boxes[rr][cc]) for rr,row in enumerate(rows) for cc,v in enumerate(row[:start])
                        if v and boxes[rr][cc] and clean(v) in ['input','output']
                        and boxes[rr][cc][1]<=cy<=boxes[rr][cc][3]]
                group=clean(groups[0][0]) if len(groups)==1 else ''
                if groups: words=[w for w in words if w[0]>=groups[0][1][2]-.2]
                label=' '.join(w[4] for w in sorted(words,key=lambda w:w[0]))
                name=clean(label);prop=None;unit=''
                if name in ['voltage[v]','current[a]'] and group in ['input','output']:
                    prop=group+('_voltage' if name=='voltage[v]' else '_current')
                    if prop=='input_current': prop='current'
                    unit='V' if name=='voltage[v]' else 'A'
                elif name=='frequency[hz]': prop='frequency';unit='Hz'
                elif name.startswith(('operatingtemp.','ambientoperatingtemperature')): prop='temperature'
                elif name.startswith(('storagetemp.','storagetemperature')): prop='storage_temperature'
                if not prop: continue
                # A unit header authorizes a bare number, not an arbitrary
                # word or reference. Keep ranges/conditions unchanged.
                display=value+' '+unit if unit and re.fullmatch(r'\d+(?:\.\d+)?',value.strip()) else value
                source=[list(boxes[hi][lc]),list(mb),list(vb)]+[list(w[:4]) for w in words]
                if groups: source.append(list(groups[0][1]))
                result.append(dict(model=model,display_model=model,property=prop,value=display,
                    unit_header=unit,
                    original_label=(group.upper()+' / ' if group else '')+label,original_value=value,
                    conditions=[],row=ri,column=ci,source_cells=source,
                    provenance='literal model column and word label inside ruled value-row band',
                    binding=dict(page=page,model=model,series='',method='ruled row-label projection',
                        summary='明示型式列・罫線付きの値セル・同じ行の仕様見出し',
                        source_cells=[list(boxes[hi][lc]),list(mb)],anchor_text=[header,model,label],matrix_cells=source)))
    return result


def join_tables(pages):
    """Return facts only for unique two-anchor joins within a heading scope."""
    identities=defaultdict(list); columns=defaultdict(list)
    for page in pages:
        if not page['series']: continue
        for table in page['tables']:
            for identity in catalogue_identities(table,page['series'],page['page']):
                identities[(identifier_key(identity['series']),identity['voltage'],identity['current'])].append(identity)
            for column in matrix_columns(table,page['series'],page['page']):
                columns[(identifier_key(column['series']),column['voltage'],column['current'])].append(column)
    result=defaultdict(list)
    model_rows=defaultdict(list)
    for values in identities.values():
        for value in values: model_rows[identifier_key(value['model'])].append(value)
    for key,values in identities.items():
        if len(values)!=1 or len(columns[key])!=1: continue
        identity=values[0]
        if len(model_rows[identifier_key(identity['model'])])!=1: continue
        column=columns[key][0]
        result[column['page']].extend(bound_properties(identity,column))
    return dict(result)


def read_document(pdf_path):
    """Geometry is taken only from the registered original, not cached text."""
    import pymupdf
    pages=[]
    with pymupdf.open(pdf_path) as pdf:
        for number,page in enumerate(pdf,1):
            words=page.get_text('words')
            headings=[w[4] for w in words if w[3]<page.rect.height*.10
                      and re.fullmatch(r'[A-Za-z0-9]+(?:[-.][A-Za-z0-9]+)*',w[4])
                      and re.search(r'[A-Za-z]',w[4]) and re.search(r'\d',w[4])]
            series=headings[0] if len(set(headings))==1 else None
            if not series: continue
            tables=[dict(rows=t.extract(),boxes=[r.cells for r in t.rows],words=words)
                    for t in page.find_tables().tables]
            pages.append(dict(page=number,series=series,tables=tables))
    return join_tables(pages)
