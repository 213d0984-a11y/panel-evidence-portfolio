"""Conservative specification evidence checks, independent of retrieval scores.

This is a bounded bilingual vocabulary, not a general semantic entailment model.
Unknown requirements fail closed. No corpus filenames, answers or page numbers.
"""
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from .lexical import identifiers, subjects, identifier_present, linked_identifier_present, identifier_key, normalize


def clean(text):
    # NFKC maps the masculine ordinal º to 'o', losing a common PDF degree
    # glyph. Repair only a temperature-unit spelling before normalization.
    text = re.sub(r'º(?=\s*[CFcf])', '°', text)
    text = unicodedata.normalize('NFKC', text).lower()
    text = re.sub(r'[‐‑‒–—−]', '-', text)
    return re.sub(r'[\s\x00-\x08\x0b\x0c\x0e-\x1f]+', '', text)


# Question aliases, evidence labels, and concrete value syntax. The vocabulary
# describes engineering properties rather than individual evaluation questions.
SPECS = {
    'voltage': (['電源電圧','動作電圧','supplyvoltage','operatingvoltage'],
                ['電源電圧','動作電圧','supplyvoltage','operatingvoltage'], r'\d+(?:\.\d+)?(?:v|kv|vac|vdc)'),
    'input_voltage': (['入力電圧','入力交流電圧','主電源','受電条件','inputvoltage'],
                ['入力電圧','入力交流電圧','主電源','受電条件','inputvoltage','supplyvoltage','電源電圧'], r'\d+(?:\.\d+)?(?:v|kv|vac|vdc)'),
    'output_voltage': (['出力電圧','outputvoltage'],
                ['出力電圧','outputvoltage'], r'\d+(?:\.\d+)?(?:v|kv|vac|vdc)'),
    'output_voltage_adjustment': (['出力電圧調整範囲','outputvoltageadjustmentrange'],
                ['出力電圧調整範囲','outputvoltageadjustmentrange','voltageadj.range'], r'\d+(?:\.\d+)?v'),
    'output_current': (['出力電流','outputcurrent'], ['出力電流','定格出力','outputcurrent','ratedoutput'], r'\d+(?:\.\d+)?(?:ma|a)'),
    'current': (['消費電流','定格電流','入力電流','inputcurrent','currentconsumption'],
                ['電流','current'], r'\d+(?:\.\d+)?(?:ma|a)'),
    'boost': (['ブースト電流','boostcurrent'], ['ブースト','boostcurrent'], r'\d+(?:\.\d+)?a'),
    'power': (['出力容量','定格容量','出力電力','定格電力','outputcapacity','powerrating','ratedpower','outputpower'], ['容量','capacity','powerrating','ratedpower','outputpower'], r'\d+(?:\.\d+)?(?:kw|w|kva)'),
    'temperature': (['温度','temperature'], ['温度','temperature'], r'[-+]?\d+(?:\.\d+)?(?:°c|ºc|℃)'),
    'storage_temperature': (['保存温度','保管温度','storagetemperature'], ['保存温度','保管温度','storagetemperature'], r'[-+]?\d+(?:\.\d+)?(?:°c|ºc|℃)'),
    'humidity': (['湿度','humidity'], ['湿度','humidity'], r'\d+(?:\.\d+)?%'),
    'protection': (['保護構造','保護等級','degreeofprotection','protectionrating'], ['保護構造','保護等級','degreeofprotection','protectiondesign','protectioncategory','environmentalprotection'], r'ip\d{2}'),
    'output_type': (['出力方式','outputtype'], ['出力','output'], r'(?:npn|pnp|opencollector|オープンコレクタ|spdt|dpdt)'),
    'wire': (['適合電線','電線サイズ','wiresize','applicablewire'], ['電線','wiresize','applicablewire'], r'(?:awg\d+|\d+(?:\.\d+)?mm2|\d+-\d+)'),
    'screw': (['端子ねじ','端子ネジ','terminalscrew'], ['ねじ','ネジ','terminalscrew'], r'm\d+(?:\.\d+)?'),
    'torque': (['締付トルク','tighteningtorque'], ['トルク','torque'], r'(?:\d+(?:\.\d+)?n[·･.]?m|n[·･.]?m.*\d)'),
    'rating': (['接点定格','接点仕様','ul/csa定格','contactrating'], ['定格','rating','voltage/','voltagecurrent'], r'\d+(?:\.\d+)?(?:a|v)'),
    'distance': (['検出距離','sensingdistance'], ['検出距離','sensingdistance'], r'\d+(?:\.\d+)?(?:mm|m)'),
    'communication_range': (['通信距離','communicationrange'], ['通信距離','communicationrange'], r'\d+(?:\.\d+)?(?:mm|m)'),
    'response': (['応答時間','responsetime'], ['応答時間','responsetime'], r'\d+(?:\.\d+)?(?:ms|s)'),
    'hysteresis': (['応差','hysteresis'], ['応差','hysteresis','differentialtravel'], r'\d+(?:\.\d+)?%'),
    'frequency': (['周波数','frequency'], ['周波数','frequency','hz'], r'\d[\d,.]*(?:khz|hz)'),
    'sound': (['音圧','soundpressure'], ['音圧','soundpressure'], r'\d+(?:\.\d+)?db'),
    'pattern': (['ブザーパターン','buzzerpattern'], ['ブザー','buzzer','beep','sound'], r'(?:beep|hi-lo|sweep|連続|断続)'),
    'dielectric': (['耐電圧','dielectricstrength'], ['耐電圧','dielectricstrength'], r'\d+(?:\.\d+)?(?:v|kv)'),
    'insulation': (['絶縁抵抗','insulationresistance'], ['絶縁抵抗','insulationresistance'], r'\d+(?:\.\d+)?m[ωΩ]'),
    'overload': (['過負荷耐量','過負荷電流','overloadcapacity'], ['過負荷','overloadcapacity','overload'], r'\d+%'),
    'speed': (['通信速度','communicationspeed','datarate'], ['通信速度','communicationspeed','datarate'], r'\d+(?:\.\d+)?(?:mbps|gbps|kbps|bps)'),
    'output': (['output?','出力は','電源定格'], ['output','出力','電源定格'], r'\d+(?:\.\d+)?(?:v|a)'),
    # A frame is a categorical code. Only a bound table cell can prove it.
    'frame': (['フレーム番号','framesize','framenumber'], [], r'\d+(?:\.\d+)*'),
    'model_number': (['型式','形名','modelnumber'], [], ''),
    'ripple': (['リップル','ripple'], ['リップル','ripple'], r'\d+(?:\.\d+)?(?:%|mv(?:p-p)?)'),
}

# Locations qualify a property; a different part on the same page is not
# interchangeable. Keep the original labels and units for human inspection.
COMPONENTS = [
    (['開放接点間','betweenopencontacts'], ['開放接点間','betweenopencontacts']),
    (['入力出力間','betweeninputandoutput','betweeninput/output'],
     ['入力出力間','betweeninputandoutput','betweeninput/output','betweenallinputterminalsandoutputterminals','betweeninputterminalsandoutputterminals']),
    (['取付ねじ','取付ネジ','mountingscrew'], ['取付ねじ','取付ネジ','mountingscrew']),
    (['電源端子','powerterminal'], ['電源端子','powerterminal','supplyterminal']),
]


@dataclass
class EvidenceCheck:
    supported: bool
    reason: str
    requirements: list[str] = field(default_factory=list)
    details: list[dict] = field(default_factory=list)


def check_evidence(question, hits, cited_pages=None):
    # Explicit, punctuated requests can refer to different subjects and fields.
    # Evaluate every clause; satisfying only the last clause is insufficient.
    clauses=re.split(r'と[、,]',question)
    if len(clauses)>1:
        checks=[check_evidence(clause,hits,cited_pages) for clause in clauses if clause.strip()]
        return EvidenceCheck(all(c.supported for c in checks),
            '各要求の根拠を確認。' if all(c.supported for c in checks) else '複数の要求の一部に根拠が不足しています。',
            list(dict.fromkeys(p for c in checks for p in c.requirements)),
            [d for c in checks for d in c.details])
    q = clean(question)
    required = [key for key,(aliases,_,_) in SPECS.items() if any(clean(a) in q for a in aliases)]
    if 'storage_temperature' in required and 'temperature' in required: required.remove('temperature')
    if 'output_voltage_adjustment' in required and 'output_voltage' in required: required.remove('output_voltage')
    needs_conditions=bool(re.search(r'適用条件|適用上の条件|applicabilityconditions',q))
    # "model ZX-10" names the subject; it does not ask us to report a model.
    # Otherwise an unknown property could pass simply because an ID exists.
    named_subject=re.sub(r'(?:型式|形名|modelnumber|model|type)\s*[a-z0-9][a-z0-9. -]*','',q)
    if 'model_number' in required and not any(a in named_subject for a in ['型式','形名','modelnumber']):
        required.remove('model_number')
    if not required:
        return EvidenceCheck(False, '質問された仕様項目を安全に解釈できません。')
    anchors = subjects(question)
    # Ignore electrical quantities as product identifiers, but keep real model IDs.
    models = [a for a in anchors if not re.fullmatch(r'(?:ac|dc)?\d+(?:\.\d+)?(?:w|v|a|hz|kw|ma|vac|vdc)', a)]
    normalized_question=normalize(question)
    model_spans=[]
    for model in models:
        pattern=r'(?<![a-z0-9])'+r'[- ]*'.join(map(re.escape,identifier_key(model)))+r'(?![a-z0-9])'
        model_spans.extend((m.start(),m.end(),model) for m in re.finditer(pattern,normalized_question))
    model_spans.sort()
    # "Series X の Model Y" is a namespace, not a third comparison operand.
    namespace_models={a[2] for a,b in zip(model_spans,model_spans[1:])
                      if normalized_question[a[1]:b[0]].strip()=='の'}
    models=[m for m in models if m not in namespace_models]
    # Do not answer only the recognized half of "voltage and <unknown field>".
    # A segment containing just a product/variant is a comparison operand.
    request_parts=re.split(r'(?<=[一-龠A-Za-z0-9])(?:と|および|及び)(?=[一-龠A-Za-z0-9])|\band\b',normalized_question)
    for part in request_parts:
        if any(clean(alias) in clean(part) for aliases,_,_ in SPECS.values() for alias in aliases): continue
        tail=part
        has_model=False
        prefix_before_model=None
        for model in models:
            pattern=r'(?<![a-z0-9])'+r'[- ]*'.join(map(re.escape,identifier_key(model)))+r'(?![a-z0-9])'
            matches=list(re.finditer(pattern,tail))
            if matches:
                if prefix_before_model is None: prefix_before_model=tail[:matches[0].start()]
                has_model=True
                tail=tail[matches[-1].end():]
        tail=re.sub(r'^(の|について|は|を|、|\s)+','',tail).strip()
        if required and re.fullmatch(r'(?:適用(?:上の)?条件(?:は.*|を.*)?[？?。]*|applicabilityconditions[?]*)',clean(tail)): continue
        if tail.startswith('単位付き') or tail in ['数値','単位','根拠','出典']: continue
        if re.fullmatch(r'(?:合格基準|判定基準|許容値|基準値)(?:は.*)?',tail): continue
        if has_model:
            # Wildcard family suffixes and capacity variants describe the
            # comparison subject, rather than an additional requested field.
            tail=re.sub(r'^(?:[-./][?□@a-z0-9]+)+','',tail)
            if re.fullmatch(r'シリーズ(?:の)?\d+(?:\.\d+)?(?:w|kw|a|v)品',tail): continue
        if has_model and re.fullmatch(r'(?:\d+極形|シリーズ|標準形|形)?',tail):
            prefix=re.sub(r'\b(?:what|is|are|the|of|for|please)\b',' ',prefix_before_model or '').strip()
            if len(prefix.split())<=1: continue
        if re.fullmatch(r'(?:nd|hd|sld|[・/\s]|定格)+',tail): continue
        if len(request_parts)>1:
            return EvidenceCheck(False,'要求された仕様項目の一部を安全に解釈できません。',required)
    pages = defaultdict(list)
    for h in hits: pages[(h.document_id,h.page_number)].append(h)
    filename_owners=defaultdict(set)
    for h in hits: filename_owners[h.file_name].add(h.document_id)
    targets = models or [None]
    generic_subject=None
    if not models and 'の' in question:
        candidate=question.split('の',1)[0]
        candidate=re.sub(r'^(この|その|登録した)','',candidate).strip()
        is_property=any(clean(a) in clean(candidate) for aliases,_,_ in SPECS.values() for a in aliases)
        if not is_property and re.search(r'[一-龠]',candidate) and len(candidate)<=25:
            generic_subject=clean(candidate)
    details=[]
    sufficient = True
    for model in targets:
        target_pages=[(key,group) for key,group in pages.items()
                      if (cited_pages is None or key in cited_pages
                          or (len(filename_owners[group[0].file_name])==1
                              and (group[0].file_name,key[1]) in cited_pages))
                      and (model is None or any(linked_identifier_present(model,h) for h in group))]
        if model is None and generic_subject:
            target_pages=[(key,group) for key,group in target_pages
                          if generic_subject in clean('\n'.join(h.text for h in group))]
        covered=set()
        for key,group in target_pages:
            if all(h.metadata.get('binding_proof_only') for h in group):
                details.append(dict(model=model,document=group[0].file_name,document_id=key[0],
                                    page=key[1],found=[],missing_qualifiers=[]))
                continue
            text='\n'.join(h.text for h in group)
            if model:
                # Explicit model-specific prose rows cannot donate their
                # properties to another product on the same page.
                retained=[]
                labels=[clean(label) for _, names, _ in SPECS.values() for label in names]
                for line in text.splitlines():
                    # A value such as IP67 AFTER "protection" is not a model.
                    # Treat only a leading identifier followed by a property
                    # label as an explicit product record.
                    compact_line=clean(line).lstrip('•*- ')
                    leading=re.match(r'^\W*([A-Z]+(?:-?[A-Z]*\d+)[A-Za-z0-9-]*)\s+', line)
                    explicit=leading is not None and any(label in compact_line for label in labels)
                    if explicit and not identifier_present(model,line):
                        continue
                    retained.append(line)
                text='\n'.join(retained)
            compact=clean(text)
            # Latin named qualifiers AFTER the product are mandatory, not OR'ed
            # with generic words (e.g. any protocol, certification, radio name).
            spans=[s for s in model_spans if s[2] in models]
            suffix=normalized_question[max(s[1] for s in model_spans):] if model_spans else question
            for si,span in enumerate(spans):
                if model==span[2]:
                    suffix=normalized_question[span[1]:spans[si+1][0] if si+1<len(spans) else len(normalized_question)]
                    if si+1<len(spans):
                        # A brand/prefix following the comparison connector
                        # belongs to the next operand, not this product.
                        suffix=re.sub(r'(?:と|および|及び)[a-z\s]*$','',suffix)
            qualifiers=re.findall(r'[A-Za-z]+(?:/[A-Za-z]+)*',suffix)
            vocabulary=set(' '.join(a for aliases,labels,_ in SPECS.values() for a in aliases+labels).lower().split())
            ignored={'what','is','the','and','of','for','please','tell','me','are','in','at','with','does','have','its',
                     'v','a','w','dc','ac','c','hz','mm','ms','mbps','how','much','many','output','current','voltage','supply','rated','input','temperature'}
            named=[term for term in qualifiers if term.lower() not in ignored
                   and not (needs_conditions and term.lower() in ['applicability','conditions'])
                   and not any(clean(term) in clean(v) for v in vocabulary)]
            requested_poles=set(re.findall(r'(\d+)(?:極|poles?)',clean(suffix)))
            missing=[term for term in named if clean(term) not in compact]
            # Bind product modifiers to the subject they follow, rather than
            # borrowing an attribute from a different comparison operand.
            for i,span in enumerate(spans):
                if model==span[2]:
                    segment=normalized_question[span[1]:spans[i+1][0] if i+1<len(spans) else len(normalized_question)]
                    if '標準形' in segment and not any(t in compact for t in ['標準形','standardmodel']):
                        missing.append('standard model')
            found=[]
            matched_facts=[]
            if not missing:
                for prop in required:
                    _,labels,pattern=SPECS[prop]
                    if prop == 'temperature' and ('温度範囲' in q or 'temperaturerange' in q):
                        pattern = r'[-+]?\d+(?:\.\d+)?(?:°c)?(?:to|[~〜～-])[-+]?\d+(?:\.\d+)?°c'
                    if prop=='model_number':
                        known=[a for a in identifiers(text) if not re.fullmatch(r'(?:ac|dc)?\d+(?:\.\d+)?(?:w|v|a|hz|kw|ma|vac|vdc)',a)]
                        if known: found.append(prop)
                        continue
                    facts=[f for h in group for f in h.metadata.get('structured_facts',[])
                           if model and identifier_key(f['model'])==identifier_key(model) and f['property']==prop]
                    # The model row is part of the proof, not optional context.
                    facts=[f for f in facts if not f.get('binding') or
                           ((key[0],f['binding']['page']) in pages and
                            any(identifier_present(f['model'],source.text)
                                for source in pages[(key[0],f['binding']['page'])]) and
                            (cited_pages is None or (key[0],f['binding']['page']) in cited_pages))]
                    if facts:
                        if any(f.get('unresolved_condition_references') for f in facts): continue
                        # Select conditions on EACH fact, not on a page-wide
                        # union that can mix a different pole/load column.
                        if prop=='rating':
                            def loads(value):
                                text=clean(value)
                                return {name for name,terms in [('resistive',['抵抗負荷','resistiveload']),
                                                                ('inductive',['誘導負荷','inductiveload'])]
                                        if any(t in text for t in terms)}
                            wanted_loads=loads(suffix)
                            shared_loads=loads(question)
                            if not wanted_loads and len(shared_loads)==1: wanted_loads=shared_loads
                            wanted_contacts=set(re.findall(r'(?<![a-z])(NO|NC)(?![a-z])',suffix,re.I))
                            wanted_contacts={v.lower() for v in wanted_contacts}
                            def qualifies(fact):
                                conditions=' '.join(fact['conditions'])
                                poles=set(re.findall(r'(\d+)(?:極|poles?)',clean(conditions)))
                                contacts={clean(c) for c in fact['conditions']} & {'no','nc'}
                                return ((not requested_poles or bool(poles & requested_poles))
                                    and (not wanted_loads or bool(loads(conditions) & wanted_loads))
                                    and (not wanted_contacts or bool(contacts & wanted_contacts)))
                            facts=[f for f in facts if qualifies(f)]
                            if not facts: continue
                            if wanted_loads and set().union(*(loads(' '.join(f['conditions'])) for f in facts))!=wanted_loads: continue
                            if wanted_contacts and not wanted_contacts<={clean(c) for f in facts for c in f['conditions']}: continue
                        alternatives=defaultdict(set)
                        for fact in facts:
                            alternatives[tuple(sorted(clean(c) for c in fact['conditions']))].add(clean(fact['value']))
                        if any(len(values)>1 for values in alternatives.values()):
                            # Two derivations for the same subject/property/
                            # condition must not silently select one value.
                            continue
                        conditions={clean(c) for f in facts for c in f['conditions']}
                        requested_conditions={clean(c) for c in named}
                        # ND/HD etc qualify the typed current values. A frame
                        # belongs to the row, not to a duty-specific column.
                        conditions_ok=(not requested_conditions or all(
                            any(term==condition or (len(term)>3 and term in condition) for condition in conditions)
                            for term in requested_conditions) or prop=='frame')
                        if requested_poles:
                            proven_poles={p for f in facts for condition in f['conditions']
                                          for p in re.findall(r'(\d+)(?:極|poles?)',clean(condition))}
                            conditions_ok=conditions_ok and proven_poles==requested_poles
                        def typed_value(fact):
                            value=clean(fact['value'])
                            # Some PDFs drop the degree glyph. Accept a C
                            # suffix only on a physically bound temperature
                            # row; never reinterpret arbitrary page numbers.
                            if prop in ['temperature','storage_temperature'] and fact.get('binding'):
                                value=re.sub(r'(?<=\d)c(?=$|[^a-z])','°c',value)
                            return value
                        def concrete(fact):
                            value=typed_value(fact)
                            if (re.search if fact.get('binding') else re.fullmatch)(pattern,value,re.I): return True
                            # A ruled row can put its unit only in the label.
                            # Validate that unit against the requested type and
                            # a leading numeric value, not a manual reference.
                            unit=fact.get('unit_header')
                            return bool(unit and fact.get('binding') and re.search(pattern,'1'+clean(unit),re.I)
                                        and re.match(r'^(?:ac|dc)?[-+]?\d+(?:\.\d+)?(?=\s|[-/+()]|$)',fact['value'],re.I))
                        values_ok=all(concrete(f) for f in facts)
                        if needs_conditions:
                            # Conditions must belong to the accepted model/
                            # property facts. A parenthesized standard code
                            # (e.g. an EN reference) is not a usage condition.
                            def applicable(fact):
                                return any(re.search(r'derat(?:ing|e)|refer|\bsee\b|参照|凍結|結露|freezing|condens|single.phase|load|\b(?:at|when|if|with|without|except|only)\b',
                                                     c,re.I) for c in fact['conditions'])
                            conditions_ok=conditions_ok and all(applicable(f) for f in facts)
                        if conditions_ok and values_ok:
                            found.append(prop)
                            matched_facts.extend(facts)
                        continue
                    if model and not identifier_present(model,text):
                        # A proven link to one field cannot donate all the
                        # unrelated properties appearing elsewhere on a page.
                        continue
                    if needs_conditions:
                        # A page excerpt alone cannot prove which condition
                        # applies to which specification.
                        continue
                    if prop == 'rating' and ('接点' in q or 'contactrating' in q):
                        labels = ['接点定格','接点仕様','contactrating']
                    for label in labels:
                        for occurrence in re.finditer(re.escape(clean(label)), compact):
                            if prop == 'rating' and not any(t in q for t in ['認証','ul/','csa','certif']):
                                prefix=compact[:occurrence.start()]
                                # General performance and certification ratings
                                # are distinct definitions, even on one page.
                                certified=max(prefix.rfind('certifiedratings'),prefix.rfind('ul-certified'),prefix.rfind('csa-certified'))
                                general=max(prefix.rfind('generalratings'),prefix.rfind('一般定格'))
                                if certified>general: continue
                            vicinity=compact[max(0,occurrence.start()-80):occurrence.start()+200]
                            if requested_poles and set(re.findall(r'(\d+)(?:極|poles?)',vicinity))!=requested_poles: continue
                            if any(any(clean(a) in q for a in aliases)
                                   and not any(clean(label) in vicinity for label in labels)
                                   for aliases,labels in COMPONENTS): continue
                            if any(term in q for term in ['合格基準','判定基準']):
                                if not any(term in vicinity for term in ['以上','以下','min.','max.','minimum','maximum']): continue
                            if prop == 'rating' and '抵抗負荷' in q:
                                # A safety/certification table with a voltage
                                # number cannot stand in for a resistive-load
                                # performance rating.
                                if not any(t in vicinity for t in ['抵抗負荷','resistiveload','cosφ=1','cosphi=1']): continue
                            # A named component/protocol elsewhere on the page
                            # does not make this property's value applicable.
                            if any(clean(term) not in vicinity for term in named): continue
                            window=compact[occurrence.start():occurrence.start()+200]
                            # Repeated headings are common. Inspect every heading,
                            # not only the first (which may describe materials).
                            if re.search(r'(notspecified|notavailable|seemanual|referto|未記載|記載なし|別紙参照)',window[:80]): continue
                            # Some prose is value-first: "5% to 90% humidity".
                            # Some specification tables put the unit in its
                            # own header before the value. Accept an explicit
                            # unit immediately followed by numbers, not a
                            # number borrowed from another specification.
                            prefix_units={'temperature':r'°c','dielectric':r'k?v(?:ac|dc)?',
                                          'voltage':r'k?v(?:ac|dc)?','input_voltage':r'k?v(?:ac|dc)?',
                                          'output_voltage':r'k?v(?:ac|dc)?',
                                          'current':r'm?a','output_current':r'm?a',
                                          'distance':r'mm','communication_range':r'mm',
                                          'response':r'ms','frequency':r'k?hz','humidity':r'%'}
                            prefix=prefix_units.get(prop)
                            unit_first=prefix and re.search(r'(?:\[?(?:'+prefix+r')\]?)[<>≤±]*[-+]?\d',window,re.I)
                            value_first=re.search(pattern,compact[max(0,occurrence.start()-80):occurrence.start()],re.I)
                            value_in_label=re.search(pattern,compact[occurrence.start():occurrence.end()],re.I)
                            if re.search(pattern,window,re.I) or unit_first or value_first or value_in_label:
                                found.append(prop)
                                break
                        if prop in found: break
            covered.update(found)
            details.append(dict(model=model,document=group[0].file_name,document_id=key[0],
                                page=key[1],found=found,missing_qualifiers=missing,matched_facts=matched_facts))
        if not set(required)<=covered:
            sufficient = False
    if not sufficient:
        return EvidenceCheck(False,'対象製品の要求仕様に直接対応する値・根拠が不足しています。',required,details)
    return EvidenceCheck(True,'要求仕様と具体値を対象製品の根拠ページ内で確認。',required,details)
