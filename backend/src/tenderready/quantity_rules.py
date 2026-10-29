"""Conservative, zero-inference quantity recovery from explicit text tables.

The parser never converts an anticipated/schedule quantity into a minimum or a
promise to purchase. It accepts only recognizable row boundaries and quantity
columns, retains exact source excerpts, and leaves ambiguous rows for review.
"""
from decimal import Decimal, InvalidOperation
import re

from .extraction_batches import plan_batches

_ANTICIPATED = re.compile(r'\bAnticipated\s+(?:Requirement|Quantit(?:y|ies))\b', re.I)
_SCHEDULE_HEADER = re.compile(r'\bItem\s+Description\s+Quantity\s+(?:Unit\s+Cost|Units?\b|Rate\b|Price\b)', re.I)
_SCOPE = re.compile(r'\b(Configuration|Lot|Variant)\s+([A-Z0-9][A-Za-z0-9.-]*)\b', re.I)
_PRODUCT = re.compile(r'(?:Tablets?|Desktops?|Laptops?|Notebooks?|Ultrabooks?|Macbooks?|Monitors?|Printers?)\b', re.I)
_ROW_START = re.compile(r'(?m)^[ \t]*\d+(?:\.\d+)?[ \t]+(?=[A-Za-z])')
_TABLE_END = re.compile(r'(?mi)^[ \t]*(?:Total|Grand\s+total|Subtotal|Quoted|\d+\.\s+[A-Z])[ \t]+')
_NUMBER = r'\d+(?:\.\d+)?'
_UNIT = re.compile(r'[ \t]*(Nos\.?|pcs\.?|pieces|sets|units)(?=\s|$)', re.I)


def _trim(text, start, end):
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def _ref(text, page, start, end, kind):
    start, end = _trim(text,start,end)
    return {'kind':kind,'text':text[start:end],'page':page,'start_offset':start,'end_offset':end}


def _scope_key(label):
    match = _SCOPE.fullmatch(label.strip())
    if match:
        return f'{match[1].casefold()}:{match[2].casefold()}'
    label = label.strip().casefold()
    return 'product:' + (label[:-1] if label.endswith('s') else label)


def _count(value):
    try:
        number = Decimal(value)
    except InvalidOperation:
        return None
    # Zero-filled BOQ cells are placeholders, never inferred purchase quantities.
    if not number.is_finite() or not 0 < number <= 1_000_000_000:
        return None
    return int(number) if number == number.to_integral_value() else str(number.normalize())


def _candidate(text, page, start, end, contexts, kind, value=None, unit=None, reason=None, value_start=None):
    start, end = _trim(text,start,end)
    excerpt = text[start:end]
    scope = next(c['text'] for c in contexts if c['kind']=='product_scope')
    amount = _count(value) if value is not None else None
    reliable = amount is not None and reason is None
    reasons = ['Quantity recovered by deterministic source reconciliation; review the stated scope and schedule before use.',
               'Anticipated quantity is not a guaranteed order or a minimum threshold.' if kind=='anticipated'
               else 'BOQ schedule quantity is not a minimum product threshold or a guaranteed purchase.']
    if reason:
        reasons.append(reason)
    elif amount is None:
        reasons.append('Quantity cell is absent, zero, or outside supported bounds; human review is required.')
    result = {'page':page,'text':excerpt,'excerpt':excerpt,'source_context':contexts,
        'start_offset':start,'end_offset':end,'category':'required_information','obligation':'unclear',
        'obligation_quote':None,'confidence':'high' if reliable else 'low',
        'review_status':'awaiting_review','requires_human_review':True,
        'review_reasons':reasons,'provenance':'deterministic_source_reconciliation',
        'numeric_conditions':[],'date_conditions':[],'quantity_conditions':[],
        'quantity_references':[],'quantity_conflict':False}
    if reliable:
        result['numeric_conditions'] = [{'operator':'unspecified','value_text':value,'unit_text':unit,'quote':excerpt}]
        result['quantity_conditions'] = [{'kind':kind,'scope':scope,'scope_key':_scope_key(scope),
            'value_text':value,'unit_text':unit,'count':amount,'operator':'unspecified','quote':excerpt,
            'value_start_offset':value_start,'value_end_offset':value_start+len(value) if value_start is not None else None}]
    return result


def _anticipated_rows(text,page):
    for batch in plan_batches(text,max_chars=10000):
        scope = next((c for c in batch.contexts if c.kind=='product_scope'),None)
        header = next((c for c in batch.contexts if c.kind=='table_header' and _ANTICIPATED.search(c.text)),None)
        if scope is None or header is None:
            continue
        contexts = [_ref(text,page,c.start,c.end,c.kind) for c in (header,scope)]
        fragment = text[batch.start:batch.end]
        # A single trailing numeric cell is distinguishable from labeled spec values.
        cells = list(re.finditer(r'(?m)^[ \t]*(' + _NUMBER + r')[ \t]*$',fragment))
        if len(cells)!=1 or fragment[cells[0].end():].strip():
            yield _candidate(text,page,batch.start,batch.end,contexts,'anticipated',reason=
                'Anticipated quantity row has ambiguous or non-trailing numeric cells; no quantity was inferred.')
            continue
        yield _candidate(text,page,batch.start,batch.end,contexts,'anticipated',value=cells[0][1],
                         value_start=batch.start+cells[0].start(1))


def _schedule_rows(text,page):
    header = _SCHEDULE_HEADER.search(text)
    if not header:
        return
    header_ref = _ref(text,page,header.start(),header.end(),'table_header')
    starts = [m for m in _ROW_START.finditer(text,header.end())
              if _PRODUCT.match(text,m.end())]
    for index,match in enumerate(starts):
        end = starts[index+1].start() if index+1 < len(starts) else len(text)
        stop = _TABLE_END.search(text,match.end(),end)
        if stop:
            end = stop.start()
        fragment = text[match.end():end]
        scope = _SCOPE.search(fragment)
        if scope:
            scope_start,scope_end = match.end()+scope.start(),match.end()+scope.end()
        else:
            product = _PRODUCT.match(fragment)
            if product is None:
                continue
            scope_start,scope_end = match.end()+product.start(),match.end()+product.end()
        contexts = [header_ref,_ref(text,page,scope_start,scope_end,'product_scope')]
        # Quantity is the immediate first column after a recognizable description;
        # following Unit Cost/tax/total cells must never become quantities.
        quantity = re.match(r'\s*(' + _NUMBER + r')(?=\s|$)',text[scope_end:end])
        if quantity is None:
            yield _candidate(text,page,match.start(),end,contexts,'schedule',reason=
                'Schedule description and quantity boundary are ambiguous; no quantity was inferred.')
            continue
        value = quantity[1]
        after = text[scope_end+quantity.end():end]
        unit = _UNIT.match(after)
        remainder = after[unit.end():] if unit else after
        # A year/model suffix embedded in the description is not a quantity.
        # Accept only numeric price cells or the recognizable zero-template text.
        remainder = re.sub(r'\b(?:INR|Rs\.?|Zero|Only)\b', '', remainder, flags=re.I)
        if re.search(r'[A-Za-z]',remainder):
            yield _candidate(text,page,match.start(),end,contexts,'schedule',reason=
                'Text follows the apparent quantity before known price columns; row alignment needs human review.')
            continue
        yield _candidate(text,page,match.start(),end,contexts,'schedule',value=value,
                         unit=unit[1] if unit else None,value_start=scope_end+quantity.start(1))


def quantity_candidates(pages):
    """Return proposals only; caller binds document IDs and persists revisions.

    Pages are dictionaries with actual ``page`` and untouched ``text`` fields.
    Matching references supplement one another; conflicting quantities remain
    separate, unapproved findings and never overwrite the source values.
    """
    rows=[]
    for page in pages:
        number,text=page['page'],page['text']
        if isinstance(number,bool) or not isinstance(number,int) or number<1 or not isinstance(text,str):
            raise ValueError('Quantity extraction requires numbered source text pages.')
        rows.extend(_anticipated_rows(text,number))
        rows.extend(_schedule_rows(text,number))
    grouped={}
    for row in rows:
        for condition in row['quantity_conditions']:
            grouped.setdefault(condition['scope_key'],[]).append(row)
    for scope_rows in grouped.values():
        values={str(r['quantity_conditions'][0]['count']) for r in scope_rows}
        conflict=len(values)>1
        for row in scope_rows:
            row['quantity_references']=[{'page':other['page'],'start_offset':other['start_offset'],
                'end_offset':other['end_offset'],'text':other['text'],
                'kind':other['quantity_conditions'][0]['kind'],'value_text':other['quantity_conditions'][0]['value_text']}
                for other in scope_rows if other is not row]
            if conflict:
                row['quantity_conflict']=True
                row['confidence']='low'
                row['review_reasons'].append('Source quantity references disagree for this product scope; human review must resolve the discrepancy.')
    return rows
