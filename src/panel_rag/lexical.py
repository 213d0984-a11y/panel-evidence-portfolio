"""Small in-memory lexical index over the existing, unchanged PDF chunks."""
import math
import re
import unicodedata
from collections import Counter


def normalize(text: str) -> str:
    text = unicodedata.normalize('NFKC', text)
    text = re.sub(r'[‐‑‒–—−﹣－]', '-', text)
    text = re.sub(r'(?<=[A-Za-z0-9])\s*-\s*(?=[A-Za-z0-9])', '-', text)
    text = re.sub(r'\b([A-Za-z]{1,3}) +(?=\d)', r'\1', text)
    text = re.sub(r'(?<=\d) +(W|V|A|Hz|kW|mA|mm|VDC|VAC)\b', r'\1', text, flags=re.I)
    return text.lower()


def identifiers(text: str) -> list[str]:
    # A space between mixed alphanumeric components is a model separator.
    value = normalize(text)
    quantity = r'(?:ac|dc)?\d+(?:\.\d+)?(?:w|kw|v|a|ma|hz|vac|vdc|mm)'
    def join_parts(match):
        left,right=match.group(1),match.group(2)
        mixed=lambda part: re.search('[a-z]',part) and re.search('[0-9]',part)
        if mixed(left) and mixed(right) and not re.fullmatch(quantity,left) and not re.fullmatch(quantity,right):
            return left+'-'+right
        return match.group(0)
    value = re.sub(r'([a-z]+\d+[a-z]*) +([a-z0-9]+)(?![a-z0-9])', join_parts, value)
    tokens = re.findall(r'[a-z0-9]+(?:[-./][a-z0-9]+)*', value)
    mixed=[t for t in tokens if re.search('[a-z]', t) and re.search('[0-9]', t)]
    # A bare decimal is normally a quantity, not a product. Promote it only
    # after an explicit model/type label; never strip its significant dots.
    numeric=re.findall(r'(?:型式|形名|\bmodel\s*|\btype\s*)(\d+(?:\.\d+)+)(?![\d.])',value)
    return list(dict.fromkeys(mixed+numeric))


def identifier_key(value):
    """Separator-insensitive identity; decimal points remain significant."""
    return re.sub(r'[-\s]', '', normalize(value))


def subjects(text):
    """Product IDs plus explicitly styled alphabetic series, not prose words."""
    value=unicodedata.normalize('NFKC',text)
    series=re.findall(r'(?<![A-Za-z0-9-])[A-Z]{2,}(?:-[A-Z]+)+(?![A-Za-z0-9-])',value)
    series+=re.findall(r'(?<![A-Za-z0-9-])[A-Z]{2,}(?=シリーズ|エンクロージャ|\s+[Ss]eries)',value)
    return list(dict.fromkeys(identifiers(text)+[s.lower() for s in series]))


def linked_identifier_present(identifier, hit):
    return identifier_present(identifier,hit.text) or any(
        identifier_key(identifier)==identifier_key(link)
        for link in hit.metadata.get('linked_models',[]))


def identifier_present(identifier: str, text: str) -> bool:
    value = normalize(text)
    # Permit separator variants, but never prefix-match a different capacity.
    pieces = re.sub(r'[- ]', '', normalize(identifier))
    pattern = r'(?<![a-z0-9])' + r'[- ]*'.join(map(re.escape, pieces))
    # An explicitly extracted alphabetic series (AB Series) may be represented
    # by numbered family members AB1/AB2. Do not extend a complete model ID,
    # and do not confuse AB with a different alphabetic prefix ABX.
    ending = r'(?![a-z])' if pieces.isalpha() else r'(?![a-z0-9.])'
    return re.search(pattern + ending, value) is not None


def terms(text: str) -> list[str]:
    value = normalize(text)
    words = re.findall(r'[a-z0-9]+', value)
    for run in re.findall(r'[\u3040-\u30ff\u3400-\u9fff]+', value):
        words.extend(run[i:i+2] for i in range(len(run)-1))
    return words


def metadata(text: str, filename: str) -> dict:
    series = re.findall(r'\b([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*)\s+[Ss]eries\b', text)
    return {'document_name': filename, 'manufacturer': None, 'category': None,
            'series': list(dict.fromkeys(series)), 'model_number': identifiers(text),
            'provenance': 'chunk text; identifiers are candidates, not verified models'}


class LexicalIndex:
    def __init__(self, hits):
        self.hits = hits
        self.counts = [Counter(terms(h.text)) for h in hits]
        self.lengths = [sum(c.values()) for c in self.counts]
        self.average = sum(self.lengths) / max(1, len(hits)) or 1
        self.df = Counter(t for c in self.counts for t in c)

    def search(self, question):
        query = set(terms(question))
        anchors = identifiers(question)
        scores = []
        for i, (hit, count) in enumerate(zip(self.hits, self.counts)):
            score = 0.0
            for term in query & count.keys():
                frequency = count[term]
                idf = math.log(1 + (len(self.hits)-self.df[term]+0.5)/(self.df[term]+0.5))
                score += idf * frequency * 2.2 / (frequency + 1.2 * (0.25 + 0.75*self.lengths[i]/self.average))
            matches = sum(identifier_present(a, hit.text) for a in anchors)
            if score > 0 or matches:
                scores.append((i, matches, score))
        return sorted(scores, key=lambda x: (-x[1], -x[2], self.hits[x[0]].chunk_id))
