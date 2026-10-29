"""Source-explicit product/configuration assignment, without similarity or DB writes.

A section heading applies only to following labelled facts on that same page.
Unknown headings, duplicate passages, and conflicting models require review.
"""
from copy import deepcopy
import re

PRODUCT_TYPES = {'datasheet', 'authorization'}


def _scope_key(text):
    value = ' '.join(text.casefold().split())
    match = re.fullmatch(r'(?:laptop\s*\(\s*)?(?:(?:product|tender)\s+)?configuration\s*:?\s*([ab])\s*\)?', value)
    if match:
        return 'configuration:' + match[1], 'Configuration ' + match[1].upper()
    if re.fullmatch(r'(?:(?:product|device)\s+type\s*:\s*)?tablets?', value):
        return 'product:tablet', 'Tablet'
    return None


def _header(text):
    parsed = _scope_key(text)
    if parsed:
        return parsed
    # Recognize ambiguous headings as boundaries, never inherit the preceding
    # configuration through them. Inline prose is not a supported heading.
    if re.match(r'^(?:(?:product|tender)\s+)?configuration\b|^(?:product|device)\s+type\s*:', text.strip(), re.I):
        return None, text.strip()
    return False


def _source_ref(context):
    return {key: context[key] for key in ('text', 'page', 'source_document_id', 'source_url', 'start_offset', 'end_offset') if key in context}


def _grounded_positions(context, spans, wid):
    text, page, did = context.get('text'), context.get('page'), context.get('source_document_id')
    if not isinstance(text, str) or not text or not isinstance(page, int) or isinstance(page, bool) or not did:
        return set()
    candidates = [span for span in spans if span.page == page and span.document_version_id == did
        and (not wid or getattr(span, 'workspace_id', wid) == wid)]
    start, end = context.get('start_offset'), context.get('end_offset')
    if start is not None or end is not None:
        if (not isinstance(start, int) or isinstance(start, bool)
                or not isinstance(end, int) or isinstance(end, bool) or end <= start):
            return set()
        return {(start, end)} if any(start >= span.start_offset and end <= span.end_offset
            and span.text[start - span.start_offset:end - span.start_offset] == text for span in candidates) else set()
    # Deduplicate overlapping source spans: they are one physical passage.
    return {(span.start_offset + match.start(), span.start_offset + match.end())
        for span in candidates for match in re.finditer(re.escape(text), span.text)}


def _page_parts(spans):
    """Merge exact overlaps, but never invent text across a missing interval."""
    parts = []
    for span in sorted(spans, key=lambda item: (item.start_offset, item.end_offset)):
        if span.end_offset - span.start_offset != len(span.text):
            return []
        if not parts or span.start_offset > parts[-1][0] + len(parts[-1][1]):
            parts.append((span.start_offset, span.text))
            continue
        start, text = parts[-1]
        overlap = min(start + len(text), span.end_offset) - span.start_offset
        if text[span.start_offset - start:span.start_offset - start + overlap] != span.text[:overlap]:
            return []
        parts[-1] = (start, text + span.text[overlap:])
    return parts


def _tender_headings(text, offset):
    """Recognize explicit table headings, including MEA's inline Tablet cell.

    A mention in ordinary prose is a blocking boundary, not an inferred header.
    The evidence parser intentionally retains its stricter whole-line grammar.
    """
    headings = []
    for line in re.finditer(r'^.*$', text, re.M):
        raw = line[0]
        quote = raw.strip()
        marker = _header(quote)
        start = line.start() + len(raw) - len(raw.lstrip())
        end = line.start() + len(raw.rstrip())
        if marker is not False:
            headings.append((offset + start, offset + end, marker[0]))
            continue
        config = re.search(r'\bconfiguration\b', raw, re.I)
        if config:
            prefix = raw[:config.start()].strip().casefold()
            parsed = _scope_key(raw[config.start():].strip()) if prefix in {'', 'of'} else None
            headings.append((offset + line.start() + config.start(), offset + end,
                             parsed[0] if parsed else None))
            continue
        tablet = re.match(r'\s*(?:\d+(?:\.\d+)?\s+)?(tablets?)\b', raw, re.I)
        if tablet:
            tail = raw[tablet.end():].strip()
            explicit = not tail or bool(re.match(r'(?:Screen\s+Size\s*:|\d+(?:\.\d+)?\b)', tail, re.I))
            headings.append((offset + line.start() + tablet.start(1),
                             offset + line.start() + tablet.end(1), 'product:tablet' if explicit else None))
    return headings


def _descriptive_prefix(text):
    # A whole table row may start with its product name before the scope cell.
    # Do not accept requirement content before that cell as belonging to it.
    text = re.sub(r'^\s*\d+(?:\.\d+)?\s*', '', text)
    tokens = re.findall(r'[^\s/()\-]+', text.casefold())
    return all(token in {'laptop', 'ultrabook', 'notebook', 'macbook', 'no', 'tebook',
                         'or', 'devices', 'of', 'similar', 'categories'} for token in tokens)


def _heading_applies(requirement, context, heading_position, spans, key):
    wid = getattr(requirement, 'workspace_id', None)
    page_spans = [span for span in spans if span.page == context['page']
        and span.document_version_id == context['source_document_id']
        and (not wid or getattr(span, 'workspace_id', wid) == wid)]
    source_id = getattr(requirement, 'source_span_id', None)
    sources = [span for span in page_spans if not source_id or span.id == source_id]
    statement = getattr(requirement, 'statement', None)
    if not isinstance(statement, str) or not statement:
        return False
    occurrences = {(span.start_offset + match.start(), span.start_offset + match.end())
        for span in sources for match in re.finditer(re.escape(statement), span.text)}
    if len(occurrences) > 1:
        # A quoted whole clause must not be confused with a substring of a
        # longer clause (e.g. Webcam versus Webcam & Speaker). Semicolons are
        # terminators, not evidence for choosing between identical clauses.
        whole = set()
        for span in sources:
            for match in re.finditer(re.escape(statement), span.text):
                before = span.text[span.text.rfind('\n', 0, match.start()) + 1:match.start()]
                line_end = span.text.find('\n', match.end())
                after = span.text[match.end():line_end if line_end >= 0 else len(span.text)]
                if not before.strip() and not after.strip(' \t\r;'):
                    whole.add((span.start_offset + match.start(), span.start_offset + match.end()))
        occurrences = whole
    if len(occurrences) != 1:
        return False
    start, end = next(iter(occurrences))
    heading_start, heading_end = heading_position
    parts = [part for part in _page_parts(page_spans) if part[0] <= min(start, heading_start)
        and part[0] + len(part[1]) >= max(end, heading_end)]
    if len(parts) != 1:
        return False
    offset, text = parts[0]
    boundaries = _tender_headings(text, offset)
    inside = [item for item in boundaries if start <= item[0] < end]
    if inside and inside[0][0] == heading_start and _descriptive_prefix(text[start - offset:heading_start - offset]):
        governing = inside[0]
    else:
        preceding = [item for item in boundaries if item[0] <= start]
        governing = preceding[-1] if preceding else None
    if not governing or governing[2] != key or not (governing[0] <= heading_start < heading_end <= governing[1]):
        return False
    return not any(governing[0] < item[0] < end for item in boundaries)


def requirement_scope(requirement, source_spans=None):
    contexts = [item for item in requirement.condition.get('source_context', []) if item.get('kind') == 'product_scope']
    if not contexts:
        return {'key': None, 'label': None, 'state': 'unscoped', 'reason': 'No product option is attached to this requirement.', 'sources': []}
    result = {'key': None, 'label': None, 'state': 'needs_review', 'sources': [_source_ref(item) for item in contexts]}
    positions = [_grounded_positions(item, source_spans or [], getattr(requirement, 'workspace_id', None)) for item in contexts]
    if not source_spans or any(len(found) != 1 for found in positions):
        return {**result, 'reason': 'The product heading could not be matched exactly to the original tender page. Review its source.'}
    parsed = [_scope_key(item['text']) for item in contexts]
    if not all(parsed) or len({item[0] for item in parsed if item}) != 1:
        return {**result, 'reason': 'The requirement has an unknown or more than one product option. Review which documents apply.'}
    key, label = parsed[0]
    if not all(_heading_applies(requirement, item, next(iter(found)), source_spans, key)
               for item, found in zip(contexts, positions)):
        return {**result, 'reason': 'The requirement is not uniquely under the cited product heading on its original page. Review its product option.'}
    return {**result, 'key': key, 'label': label, 'state': 'scoped',
        'reason': f'The original tender heading explicitly identifies {label}.'}


def _heading_fact(span, quote, key, label):
    return {'field': 'product_scope', 'raw_value': label, 'normalized': {
        'value': key, 'quote': quote, 'method': 'explicit_product_scope_v1',
        'source_span_id': span.id, 'page': span.page, 'document_version_id': span.document_version_id,
        'authenticity': 'not_independently_verified'}}


def _document_scope(doc, spans, facts, required):
    by_page, by_span, headings = {}, {}, []
    for span in spans:
        if span.document_version_id != doc.id or getattr(span, 'workspace_id', None) != getattr(doc, 'workspace_id', None):
            raise ValueError('Scope spans must belong to the same workspace and document.')
        by_span[span.id] = span
        for match in re.finditer(r'^.*$', span.text, re.M):
            quote = match[0].strip()
            marker = _header(quote)
            if marker is False:
                continue
            key, label = marker
            item = {'position': span.start_offset + match.start(), 'key': key,
                'fact': _heading_fact(span, quote, key, label)}
            by_page.setdefault(span.page, []).append(item)
            headings.append(item)
    for items in by_page.values():
        items.sort(key=lambda item: item['position'])
    selected, issues = [], []
    selected_headers = {}
    for fact in facts:
        reference = fact.get('normalized', {})
        span = by_span.get(reference.get('source_span_id'))
        if span is None or reference.get('document_version_id') != doc.id or reference.get('page') != span.page:
            issues.append('A document fact has no matching source page.')
            continue
        quote = reference.get('quote', '')
        occurrences = list(re.finditer(r'^\s*' + re.escape(quote) + r'\s*$', span.text, re.M)) if quote else []
        if len(occurrences) != 1:
            issues.append('A repeated or unclear passage cannot be assigned to one product option.')
            continue
        position = span.start_offset + occurrences[0].start()
        preceding = [item for item in by_page.get(span.page, []) if item['position'] < position]
        header = preceding[-1] if preceding else None
        if not header or not header['key']:
            issues.append('Some document details have no clear product heading on the same page.')
            continue
        if header['key'] != required['key']:
            continue
        scoped = deepcopy(fact)
        scoped['normalized']['product_scope'] = required['key']
        scoped['normalized']['scope_sources'] = [deepcopy(header['fact']['normalized'])]
        selected.append(scoped)
        ref = header['fact']['normalized']
        selected_headers[(ref['source_span_id'], ref['quote'])] = header['fact']
    matching = [item for item in headings if item['key'] == required['key']]
    unknown = any(item['key'] is None for item in headings)
    if unknown:
        issues.append('The document contains an unknown or ambiguous product heading.')
    if not headings:
        issues.append('The document does not explicitly name a supported product option.')
    if matching and not selected:
        issues.append('The matching product heading has no clearly assigned document details.')
    models = {fact['normalized']['value'] for fact in selected if fact['field'] == 'model'}
    if None in models or len(models) > 1:
        issues.append('The document gives unclear or different models for the same product option.')
        selected = []
    return selected, list(selected_headers.values()), list(dict.fromkeys(issues)), headings


def scope_evidence(requirement, by_doc, spans_by_doc, requirement_spans=None):
    """Return the usual (document, library entry, facts) tuples with scoped facts.

    No cross-page header inheritance, guessed product assignments, or approvals.
    Header facts can be persisted by the existing verification check() helper.
    """
    required = requirement_scope(requirement, requirement_spans)
    summary = {'label': required['label'], 'state': 'unscoped', 'reason': required['reason'], 'documents': []}
    result = {'required_scope': required, 'by_doc': dict(by_doc), 'checks': [],
        'matched': False, 'requires_review': False, 'summary': summary}
    if required['state'] == 'unscoped':
        return result
    products = {did: item for did, item in by_doc.items() if item[1].evidence_type in PRODUCT_TYPES}
    result['by_doc'] = {did: item for did, item in by_doc.items() if did not in products}
    if required['state'] == 'needs_review':
        summary['state'] = 'needs_review'
        result['requires_review'] = True
        result['checks'].append({'outcome': 'review', 'rationale': required['reason'], 'facts': [], 'document_id': None})
        return result
    assigned_models = set()
    for did, (doc, entry, facts) in products.items():
        if did != doc.id or getattr(doc, 'workspace_id', None) != getattr(requirement, 'workspace_id', None):
            raise ValueError('Scope documents must belong to the requirement workspace.')
        selected, refs, issues, headings = _document_scope(doc, spans_by_doc.get(did, []), facts, required)
        if selected:
            result['by_doc'][did] = (doc, entry, selected)
            summary['documents'].append({'id': did, 'filename': doc.filename})
            assigned_models.update(f['normalized']['value'] for f in selected if f['field'] == 'model')
            result['checks'].append({'outcome': 'pass', 'rationale': f'{doc.filename}: document details are under an explicit {required["label"]} heading on the same page.', 'facts': refs, 'document_id': did})
        elif headings and not issues:
            result['checks'].append({'outcome': 'not_applicable', 'rationale': f'{doc.filename}: its product heading is for a different option, so its details were not used for {required["label"]}.', 'facts': [item['fact'] for item in headings], 'document_id': did})
        for reason in issues:
            result['requires_review'] = True
            result['checks'].append({'outcome': 'review', 'rationale': f'{doc.filename}: {reason}', 'facts': refs, 'document_id': did})
    if len(assigned_models) > 1:
        result['requires_review'] = True
        result['checks'].append({'outcome': 'review', 'rationale': f'Documents name different models for {required["label"]}. Review the intended model before relying on these checks.', 'facts': [], 'document_id': None})
    result['matched'] = bool(summary['documents']) and not result['requires_review']
    if result['requires_review']:
        summary.update(state='needs_review', reason='Some document details cannot be assigned to one product option safely. Review the cited headings and models.')
    elif summary['documents']:
        summary.update(state='matched', reason=f'Documents explicitly identify {required["label"]}; only facts under matching headings are used.')
    else:
        summary.update(state='missing', reason=f'No company document explicitly identifies {required["label"]}. Upload evidence for that product option.')
        result['checks'].append({'outcome': 'missing', 'rationale': summary['reason'], 'facts': [], 'document_id': None})
    return result
