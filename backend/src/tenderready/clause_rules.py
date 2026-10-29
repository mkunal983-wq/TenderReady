"""Conservative, offline corrections grounded in exact original page text.

These rules do not claim general procurement interpretation. They repair bounded
patterns and retain ambiguous language for human review. No LLM, network or DB
writes occur here; the caller versions proposals and retains prior decisions.
"""
from copy import deepcopy
import re

RULES_VERSION = 'source-clause-rules-v1'
_NUMBERED = re.compile(r'(?m)^[ \t]*(?:\d+(?:\.\d+)*[.)]|\d+\.\d+)[ \t]+(?=\S)')
_HEADING = re.compile(r'(?m)^[ \t]*(?:[A-Z][A-Z /&-]{5,}|Cover\s+\d+\s*[-–].*)[ \t]*$')
_DIRECTIVE = re.compile(r'\b(?:must|shall|should|required|compulsory|mandatory|responsible)\b', re.I)
_BIDDER_ENCRYPT = re.compile(r'\b(?:bidder|supplier|tenderer)s?\s+(?:must|shall|is required to|are required to)\s+(?:encrypt|use|provide|ensure)', re.I)


def _pages(pages):
    return pages if isinstance(pages, dict) else {p['page']: p['text'] for p in pages}


def _clean_condition(c):
    return {k: v for k, v in c.items() if k not in {'page', 'source_document_id', 'source_url'}}


def _unique_offset(text, quote):
    first = text.find(quote)
    return first if first >= 0 and text.find(quote, first + 1) < 0 else None


def _clause_at(text, offset, quote_end):
    starts = [m.start() for m in _NUMBERED.finditer(text)]
    previous = [s for s in starts if s <= offset]
    if not previous:
        return None
    start = previous[-1]
    ends = [s for s in starts if s > start]
    ends += [m.start() for m in _HEADING.finditer(text) if m.start() > start]
    end = min(ends, default=len(text))
    if quote_end > end or end - start > 6000:
        return None
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def _procedural_extent(source, quote):
    """Extend only known complete numbered clauses, never across pages."""
    offset = _unique_offset(source, quote)
    if offset is None:
        return None
    bounds = _clause_at(source, offset, offset + len(quote))
    if bounds:
        block = source[bounds[0]:bounds[1]]
        anchored = (re.search(r'\b(?:BOQ|FOD)\b|\bFree\s+on\s+Delivery\b', block, re.I)
                    or (re.search(r'\b(?:EMD|Earnest\s+Money\s+Deposit)\b', block, re.I)
                        and re.search(r'original\s+hard\s+copy|sealed\s+envelope', block, re.I)))
        if anchored and block != quote:
            return bounds
    # BOQ cover-note continuation has no numbered clause; require a single
    # blank-line-delimited paragraph containing an explicit submission directive.
    if len(quote) < 500 and re.search(r'\bBOQ\b|^Along with the Tender document$', quote, re.I):
        blank = list(re.finditer(r'\n[ \t]*\n', source))
        start = max([m.end() for m in blank if m.end() <= offset], default=0)
        end = min([m.start() for m in blank if m.start() >= offset + len(quote)], default=len(source))
        block = source[start:end].strip()
        if (len(block) <= 1500 and block != quote
                and re.search(r'Bid\s+to\s+be\s+submitted\s+online\s+in\s+prescribed\s+BOQ', block, re.I)):
            start = source.find(block, start, end)
            return start, start + len(block)
    return None


def reconcile_clause(row, pages):
    """Return a new flat requirement proposal with audit metadata, or None.

    Input is a requirements_response-style row. Original IDs are retained only
    for the caller to establish a version link, never as an instruction to mutate
    a record. New text/excerpts and all condition quotations are exact substrings
    of the supplied page. Ambiguous/duplicated source locations are not guessed.
    """
    page_map = _pages(pages)
    source = page_map.get(row.get('page'), '')
    original = row.get('text', row.get('statement', ''))
    offset = _unique_offset(source, original) if original else None
    if offset is None:
        return None
    previous = row.get('reconciliation', {})
    if previous.get('method') == RULES_VERSION and previous.get('evidence') and all(
            page_map.get(e.get('page'), '')[e.get('start_offset', 0):e.get('end_offset', 0)] == e.get('text')
            for e in previous.get('evidence', [])):
        return None
    out = deepcopy(row)
    rules, reasons = [], []

    def note(rule, reason):
        if rule not in rules:
            rules.append(rule)
            reasons.append(reason)

    extent = _procedural_extent(source, original)
    if extent:
        out['text'] = out['excerpt'] = source[extent[0]:extent[1]]
        note('complete_same_page_procedure', 'Restored the complete same-page procedural clause, including its continuation; verify the full source before approval.')
    text = out.get('text', original)
    numeric = [_clean_condition(c) for c in out.get('numeric_conditions', [])]
    dates = [_clean_condition(c) for c in out.get('date_conditions', [])]

    # An event timing rule is not an absolute date and cannot mean "on or after".
    delivery = re.search(r'\bat\s+the\s+time\s+of\s+delivery(?:\s+of\s+goods)?\b|\bat\s+delivery\b', text, re.I)
    ambiguous_validity = re.search(r'\bvalid\s+up\s+to\s+[^.;\n]{1,80}\bmonths?\b', text, re.I)
    if delivery and re.search(r'\b(?:guarantee|security|bond)\b', text, re.I):
        unrelated = [c for c in dates if not re.search(r'\bdelivery\b', c.get('boundary_text', ''), re.I) and not (ambiguous_validity and re.search(r'\bmonths?\b', c.get('boundary_text', ''), re.I))]
        if ambiguous_validity:
            boundary = text[ambiguous_validity.start():delivery.end()] if delivery.end() >= ambiguous_validity.end() else text
            dates = [*unrelated, {'relation': 'unspecified', 'boundary_text': boundary, 'quote': text}]
            note('ambiguous_validity', 'The source combines an upper-duration phrase with a delivery event. No minimum validity or calendar expiry is inferred; clarification is required.')
        else:
            dates = [*unrelated, {'relation': 'relative', 'boundary_text': delivery.group(), 'quote': text}]
            out['temporal_conditions'] = [{'kind': 'event', 'event_text': delivery.group(), 'relation': 'at_event', 'quote': text}]
            note('at_event_not_after', 'The guarantee is due at the delivery event, not on-or-after an inferred calendar date. No calendar deadline is invented.')

    # Keep the exact written currency/amount and an unanchored repeating period.
    if re.search(r'\bturnover\b', text, re.I):
        amount = re.search(r'\bminimum\s+turnover\s+of\s+(?P<currency>Rs\.|INR|₹)\s*(?P<amount>(?:[\d,]+(?:\.\d+)?|[A-Za-z-]+)(?:\s+(?:lakhs?|crores?|million|thousand))?)\s+per\s+annum', text, re.I)
        period = re.search(r'\bduring\s+each\s+of\s+the\s+last\s+(?:\d+|[A-Za-z-]+)\s+years?\b', text, re.I)
        if amount and period:
            numeric = [{'operator': '>=', 'value_text': amount['amount'], 'unit_text': amount['currency'], 'quote': text}]
            dates = [{'relation': 'relative', 'boundary_text': period.group(), 'quote': text}]
            out['temporal_conditions'] = [{'kind': 'repeating_period', 'period_text': period.group(), 'frequency_text': re.search(r'per\s+annum', text, re.I).group(), 'anchor_date': None, 'quote': text}]
            note('turnover_each_period', 'Preserved the written currency and amount for each stated year. The reference date and financial-year boundaries are unspecified; no aggregate or invented calendar years are used.')

    optional_scan = re.search(r'\b(?:documents\s+)?may\s+be\s+scanned\s+with\s+\d+(?:\.\d+)?\s*dpi\b', text, re.I)
    if optional_scan:
        advisory = [c for c in numeric if re.fullmatch(r'dpi', c.get('unit_text') or '', re.I)]
        numeric = [c for c in numeric if c not in advisory]
        out['advisory_conditions'] = [{'kind': 'optional_scan_resolution', **c} for c in advisory]
        # Whole mixed paragraph includes preparation advice too; do not claim all
        # of it is optional or mandatory based on the single scanning sentence.
        out['obligation'] = 'unclear'
        out['obligation_quote'] = None
        out['disposition'] = 'advisory'
        note('optional_scan_not_threshold', 'Scanning resolution is optional advice ("may be scanned"), not a supplier acceptance threshold. Example file formats are not made mandatory by this clause.')

    # Numbers in protocol/version labels are not measurement units.
    if re.search(r'\bUSB\b', text, re.I):
        version_conditions = [c for c in numeric if re.search(r'\d+\.\d+', c.get('unit_text') or '')]
        if version_conditions:
            numeric = [c for c in numeric if c not in version_conditions]
            out['unresolved_interpretations'] = [{'kind': 'usb_port_version_count', 'quote': text,
                'reason': 'Separate port counts from USB version identifiers before defining checks.'}]
            note('usb_version_not_unit', 'USB version identifiers are not numerical measurement units. Original port specification is retained; count/version mapping needs review.')

    # Passive platform descriptions are not obligations to implement encryption.
    portal_encryption = (re.search(r'\bdocuments\b.*\bwould\s+be\s+encrypted\b', text, re.I | re.S)
        and re.search(r'\b(?:server|portal|bid\s+openers)\b', text, re.I)
        and not _DIRECTIVE.search(text)
        and not _BIDDER_ENCRYPT.search(text))
    helpdesk = (re.search(r'\b(?:queries|help)\b', text, re.I) and re.search(r'\bHelpdesk\b', text, re.I)
                and not _DIRECTIVE.search(text))
    contact = (re.search(r'\b(?:Tel|Telephone)\b', text, re.I) and re.search(r'\bFax\b', text, re.I)
               and re.search(r'e-?mail', text, re.I) and not _DIRECTIVE.search(text)
               and not re.search(r'\b(?:submit|deliver|upload|send|pay)\b', text, re.I))
    if portal_encryption or helpdesk or contact:
        out['disposition'] = 'reference'
        out['category'] = 'manual_review'
        out['obligation'] = 'unclear'
        out['obligation_quote'] = None
        numeric, dates = [], []
        note('reference_not_supplier_rule', 'This passage describes portal behavior or provides issuing-authority/helpdesk reference information; it is not a supplier evidence or product threshold.')

    # Explicit advice cannot be promoted by an unsupported model rationale.
    if re.search(r'\bbidders?\s+are\s+advised\b', text, re.I) and not _DIRECTIVE.search(text):
        out['obligation'] = 'unclear'
        out['obligation_quote'] = None
        out.setdefault('disposition', 'advisory')
        note('advice_not_mandatory', 'The source says "advised" without a mandatory cue. No mandatory obligation is inferred from model-generated rationale.')

    if not rules:
        return None
    # All rules leave interpretations needing approval; none is official verification.
    out['numeric_conditions'], out['date_conditions'] = numeric, dates
    out.setdefault('disposition', 'requirement')
    out['requires_human_review'] = True
    out['review_status'] = 'awaiting_review'
    out['provenance'] = 'deterministic_source_reconciliation'
    out['previous_model_review_reasons'] = deepcopy(row.get('previous_model_review_reasons', row.get('review_reasons', [])))
    out['review_reasons'] = reasons
    begin = _unique_offset(source, text)
    if begin is None:
        return None
    out['reconciliation'] = {'method': RULES_VERSION, 'rules': rules, 'evidence': [
        {'page': row['page'], 'text': text, 'start_offset': begin, 'end_offset': begin + len(text)}]}
    return None if out == row else out


def procedural_candidates(pages):
    """Recover only explicitly labeled financial-upload format rows."""
    result = []
    for page, text in _pages(pages).items():
        for match in re.finditer(r'(?m)^\s*\d+\.\s+Financial\s+bid\s+as\s+per\s+[^\n]+\.(?:xls|xlsx)\b[^\n]*', text, re.I):
            prefix = text[max(0, match.start()-220):match.start()]
            if not re.search(r'Cover\s+\d+\s*[-–]\s*\(Financial\s+Bid\)', prefix, re.I) or not re.search(r'File\s+Type', prefix, re.I):
                continue
            quote = match.group().strip()
            offset = text.find(quote,match.start(),match.end())
            result.append({'page':page,'text':quote,'excerpt':quote,'category':'required_information',
                'obligation':'unclear','obligation_quote':None,'numeric_conditions':[],'date_conditions':[],
                'confidence':'low','requires_human_review':True,'review_status':'awaiting_review',
                'review_reasons':['Recovered an explicit financial-bid file-format checklist row; review its cover context before submission.'],
                'provenance':'deterministic_source_reconciliation','disposition':'requirement',
                'reconciliation':{'method':RULES_VERSION,'rules':['financial_upload_format'],
                    'evidence':[{'page':page,'text':quote,'start_offset':offset,'end_offset':offset+len(quote)}]}})
    return result
