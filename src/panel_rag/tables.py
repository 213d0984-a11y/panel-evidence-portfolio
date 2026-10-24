"""Optional, conservative table evidence. No imputation of merged/empty cells."""
import re
from .lexical import identifiers, normalize


def model_column_facts(rows, requested):
    """Accept exact, unique model columns only; keep original labels/values."""
    result=[]
    def key(value):
        return re.sub(r'[-\s]', '', normalize(value))
    for header_index, row in enumerate(rows):
        columns={i:cell.strip() for i,cell in enumerate(row)
                 if isinstance(cell,str) and len(cell)<70
                 and re.fullmatch(r'[A-Za-z0-9]+(?:[-.][A-Za-z0-9]+)+',cell.strip())
                 and re.search(r'\d',cell) and re.search(r'[A-Za-z]',cell)}
        if len(columns)<2:
            continue
        first=min(columns)
        for target in requested:
            matches=[i for i,name in columns.items() if key(name)==key(target)]
            if len(matches)!=1: continue
            column=matches[0]
            for row_index, values in enumerate(rows[header_index+1:],header_index+1):
                if len(values)!=len(row): break
                labels=[v.strip() for v in values[:first] if isinstance(v,str) and 0<len(v.strip())<100]
                value=values[column]
                if not labels or not isinstance(value,str) or not value.strip() or len(value)>200: continue
                result.append(dict(model=columns[column],property=' / '.join(labels),value=value.strip(),
                                   row=row_index,column=column,header_row=header_index))
        break
    return result


def extract_table_facts(pdf_path, page_number, question):
    import pymupdf
    facts=[]
    with pymupdf.open(pdf_path) as pdf:
        page=pdf[page_number-1]
        for index,table in enumerate(page.find_tables().tables):
            for fact in model_column_facts(table.extract(),identifiers(question)):
                cell=table.rows[fact['row']].cells[fact['column']]
                if cell is None: continue
                # A spanning cell must not be passed off as a per-model value.
                header=table.rows[fact['header_row']].cells[fact['column']]
                if header is None or cell[0]<header[0]-2 or cell[2]>header[2]+2: continue
                facts.append({**fact,'table':index,'bbox':list(cell),
                              'provenance':'explicit model column; no merged-cell fill'})
    return facts
