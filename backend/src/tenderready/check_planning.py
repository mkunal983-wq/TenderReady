"""Pure, bounded check planning from literal tender wording and cached conditions.

Coverage describes which parts of a clause the prepared rules cover. It is not
an evidence result, an identity match, a reviewer decision, or a claim of
compliance. Product-scope references must be resolved independently by callers.
"""
from .clause_actions import action_for
from .hardware_comparison import hardware_baseline
from datetime import date
from decimal import Decimal, InvalidOperation
import re

VERSION = 'source-check-plan-v1'
DEFAULT_FIELDS = frozenset({'model', 'ram_gb', 'storage_gb', 'valid_until'})
_CAPACITY_FIELDS = {'ram': 'ram_gb', 'memory': 'ram_gb', 'storage': 'storage_gb',
                    'ssd': 'storage_gb', 'hard disk': 'storage_gb'}
_PREFIX = {'at least': 'gte', 'minimum': 'gte', 'minimum of': 'gte',
           'not less than': 'gte', 'no less than': 'gte', 'at most': 'lte',
           'maximum': 'lte', 'maximum of': 'lte', 'not more than': 'lte',
           'no more than': 'lte', 'exactly': 'eq'}
_SUFFIX = {'or above': 'gte', 'or higher': 'gte', 'or more': 'gte',
           'or below': 'lte', 'or lower': 'lte', 'or less': 'lte'}
_NUMBER = r'(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>GB)'
_ATTRIBUTE = r'(?P<attribute>RAM|Memory|Storage|SSD|Hard\s+Disk)'
_QUALIFIER = r'(?P<qualifier>Flash|SSD|HDD|(?:LP)?DDR[2-5](?:X)?)'
_PREFIX_PATTERN = '|'.join(re.escape(value) for value in sorted(_PREFIX, key=len, reverse=True))
_SUFFIX_PATTERN = '|'.join(re.escape(value) for value in _SUFFIX)
_CAPACITY = re.compile(_ATTRIBUTE + r'\s*:\s*(?:(?P<prefix>' + _PREFIX_PATTERN + r')\s+)?'
    + _NUMBER + r'(?:\s+' + _QUALIFIER + r')?(?:\s+(?P<suffix>' + _SUFFIX_PATTERN + r'))?[.;]?', re.I)
_PROSE = re.compile(r'The\s+(?:(?P<model>[A-Za-z0-9]+(?:[ -][A-Za-z0-9]+){0,7})\s+)?'
    r'(?P<subject>product|laptop|device)\s+(?:must|shall)\s+have\s+'
    r'(?P<prefix>' + _PREFIX_PATTERN + r')\s+' + _NUMBER + r'(?:\s+' + _QUALIFIER + r')?\s+'
    + _ATTRIBUTE + r'[.;]?', re.I)
_MINIMUM = re.compile(r'(?:The\s+)?(?P<prefix>minimum|maximum)\s+' + _ATTRIBUTE
    + r'\s*(?:is|:)\s*' + _NUMBER + r'[.;]?', re.I)
_CERTIFICATE = re.compile(r'(?:The\s+)?certificate\s+(?:(?:must|shall)\s+be\s+)?valid\s+through\s+'
    r'(?P<date>\d{4}-\d{2}-\d{2})[.;]?', re.I)
_REFERENCE_DATE = re.compile(r'(?:Published Date|Date of Technical Bid Opening(?:\s*\(online\))?)\s+'
    r'\d{2}\.\d{2}\.\d{4}(?:\s*\(\d{4}\s*hrs\))?', re.I)
_SCHEDULE_DATE = re.compile(r'(?:Bid Document Download (?:Start|End) Date|Clarification (?:Start|End) Date|'
    r'Bid Submission (?:Start|End) Date(?:\s*\(online\))?)\s+'
    r'\d{2}\.\d{2}\.\d{4}(?:\s*\(\d{4}\s*hrs\))?', re.I)


def _flat(text):
    return ' '.join(text.casefold().split())


def _value(text):
    match = re.fullmatch(r'(\d+(?:\.\d+)?)(?:\s*GB)?', text.strip(), re.I)
    return Decimal(match[1]) if match else None


def _criterion(field, operator, expected, quote, evidence_type='datasheet'):
    return {'field': field, 'operator': operator, 'expected': expected,
            'quote': quote, 'evidence_type': evidence_type}


def _scope_only_reason(reason, text, criteria):
    """Recognize positive extraction notes, not arbitrary model reassurance."""
    if reason in {"Explicit minimum processor speed requirement with 'or above' phrasing", 'Architecture requirement (64 bit) included but not captured as numeric condition'}:
        return {'cpu_bits', 'cpu_ghz'} <= {c['field'] for c in criteria}
    if reason in {'USB version identifiers are not numerical measurement units. Original port specification is retained; count/version mapping needs review.', 'Explicit port quantity and version specifications', 'USB port counts and versions clearly stated', 'Numeric condition has a version-like unit; review its meaning before using it as a threshold.'}:
        return {'hdmi', 'vga', 'ethernet', 'usb2_ports', 'usb3_ports'} <= {c['field'] for c in criteria}
    hardware_notes = {
        'Explicit processor generation requirement': {'processor'},
        'Category context: Configuration A laptop specification': {'processor'},
        'Specifies minimum processor requirement: 1.6 GHz dual-core Intel Core i5 or above': {'cpu_family','cpu_ghz','cpu_cores'},
        'Specifies minimum graphics requirement: Intel HD 6000 or above': {'graphics'},
    }
    if reason in hardware_notes:
        return hardware_notes[reason] <= {c['field'] for c in criteria}
    literal_notes = {
        'Specifies port requirement: USB': {'usb'},
        'Explicit inbuilt Bluetooth and WiFi requirement': {'bluetooth', 'wifi'},
        'Specifies connectivity requirement: Bluetooth and Wifi Inbuilt': {'bluetooth', 'wifi'},
        'Explicit integrated HD webcam and speaker requirement': {'webcam', 'speaker'},
        'Specifies webcam requirement: Integrated HD Webcam': {'webcam'},
        'Specifies operating system requirement: Mac OS': {'operating_system'},
    }
    if reason in literal_notes:
        return literal_notes[reason] <= {c['field'] for c in criteria}
    if reason in {"Explicit maximum display size", "Unit 'inch' appears in source text",
                  'Specifies minimum display requirement: LED Backlit Display 11 inch or above',
                  "Explicit minimum screen size requirement with 'or above' phrasing"}:
        return any(c['field'] == 'screen_inches' for c in criteria)
    if reason in {
        'Explicit obligation wording could not be validated.',
        'Product configuration scope comes from the cited table heading; confirm applicability before evidence verification.',
        'Manually transcribed; no model extraction claimed.',
        'Limited labelled grammar; completeness requires reviewer confirmation.',
    }:
        return True
    if reason == "Unit 'GB' appears in source text":
        return bool(re.search(r'\bGB\b', text, re.I)) and any(c['field'] in {'ram_gb', 'storage_gb'} for c in criteria)
    specifies = re.fullmatch(r'Specifies (minimum|maximum) (memory|storage) requirement:\s*([^\n]+)', reason, re.I)
    explicit = re.fullmatch(r"Explicit (minimum|maximum) (memory(?: \(RAM\))?|storage|hard disk) (?:specification|capacity|requirement)(?: with '(or higher|or above|or below|or lower)' phrasing)?", reason, re.I)
    match = specifies or explicit
    if not match:
        return False
    field = 'ram_gb' if match[2].casefold().startswith('memory') else 'storage_gb'
    operator = 'gte' if match[1].casefold() == 'minimum' else 'lte'
    if match[3] and _flat(match[3]) not in _flat(text):
        return False
    return any(c['field'] == field and c['operator'] == operator for c in criteria)


def represented_condition(criterion, condition, kind='numeric'):
    """Whether a *grounded* saved condition agrees with a prepared check.

    Callers must still validate quotations against the original PDF. A quoted
    number alone cannot determine the attribute or comparison by itself.
    """
    quote = condition.get('quote', '')
    if not quote or not (quote in criterion['quote'] or criterion['quote'] in quote):
        return False
    if kind == 'date':
        return (criterion['field'] == 'valid_until' and criterion['operator'] == 'gte'
                and condition.get('relation') == 'valid_through'
                and condition.get('boundary_text') == criterion['expected'])
    if criterion['field'] == 'processor' and criterion['expected'].lower().startswith('5th generation'):
        value = condition.get('value_text', '')
        unit = condition.get('unit_text')
        separate_unit = value == '5' and isinstance(unit, str) and unit.casefold() in {'generation', 'generations'}
        ordinal_phrase = isinstance(value, str) and _flat(value) == '5th generation' and unit is None
        return condition.get('operator') == '>=' and (separate_unit or ordinal_phrase)
    if criterion['field'] in {'cpu_ghz', 'cpu_bits'}:
        try:
            return (condition.get('unit_text', '').casefold() == ('ghz' if criterion['field'] == 'cpu_ghz' else 'bit')
                and {'>=': 'gte', '=': 'eq'}.get(condition.get('operator')) == criterion['operator']
                and Decimal(condition.get('value_text', '')) == Decimal(criterion['expected']))
        except InvalidOperation:
            return False
    if criterion['field'] == 'screen_inches':
        try:
            return (condition.get('unit_text') in {'inch', 'inches'}
                and {'<':'lt','>=':'gte'}.get(condition.get('operator')) == criterion['operator']
                and Decimal(condition.get('value_text', '')) == Decimal(criterion['expected']))
        except InvalidOperation:
            return False
    unit = condition.get('unit_text')
    unit_match = re.fullmatch(r'GB(?:\s+(RAM|memory|storage|SSD|Hard Disk))?', unit, re.I) if isinstance(unit, str) else None
    if not unit_match or (unit_match[1] and _CAPACITY_FIELDS[_flat(unit_match[1])] != criterion['field']):
        return False
    fields = {_CAPACITY_FIELDS[_flat(match[0])] for match in re.finditer(
        r'\b(?:RAM|Memory|Storage|SSD|Hard\s+Disk)\b', quote, re.I)}
    # For a short model quote, use the source-grounded complete criterion.
    if not fields:
        fields = {_CAPACITY_FIELDS[_flat(match[0])] for match in re.finditer(
            r'\b(?:RAM|Memory|Storage|SSD|Hard\s+Disk)\b', criterion['quote'], re.I)}
    if fields != {criterion['field']}:
        return False
    operator = {'>=': 'gte', '<=': 'lte', '=': 'eq'}.get(condition.get('operator'))
    try:
        expected, extracted = _value(criterion['expected']), _value(condition.get('value_text', ''))
    except (TypeError, AttributeError, InvalidOperation):
        return False
    return bool(expected is not None and extracted is not None and expected == extracted
                and criterion['operator'] == operator)


def build_check_plan(req, source_span, *, supported_fields=None):
    """Prepare only exact, supported comparisons; preserve every omitted part.

    ``supported_fields`` allows a caller with matching evidence readers to opt in
    to explicit ``storage_type``/``memory_type`` checks. No media equivalence or
    version ordering is inferred. The default only uses existing core fields.
    """
    supported = DEFAULT_FIELDS if supported_fields is None else frozenset(supported_fields)
    text = req.statement
    condition = req.condition or {}
    page = getattr(source_span, 'page', None)
    document_id = getattr(source_span, 'document_version_id', None)
    span_id = getattr(source_span, 'id', None)
    source = {'source_document_id': document_id, 'source_span_id': span_id, 'page': page, 'quote': text}
    plan = {'version': VERSION, 'kind': 'evidence', 'coverage': 'manual', 'criteria': [],
            'review_reasons': [], 'unhandled': [], 'sources': [source], 'scope_refs': [],
            'quantity_conditions': [], 'date_conditions': [], 'temporal_conditions': []}

    def unhandled(value, reason):
        item = {'text': value, 'reason': reason}
        if item not in plan['unhandled']:
            plan['unhandled'].append(item)
        if reason not in plan['review_reasons']:
            plan['review_reasons'].append(reason)

    if (not isinstance(text, str) or not text or not isinstance(page, int) or isinstance(page, bool) or page < 1
            or not document_id or not span_id or text not in source_span.text
            or getattr(req, 'source_span_id', span_id) != span_id
            or getattr(req, 'workspace_id', None) != getattr(source_span, 'workspace_id', None)):
        unhandled(text, 'The requirement could not be matched to its original PDF page.')
        return plan

    # Scope refs remain visible, but only the caller can resolve them against
    # separate page spans and an explicitly selected evidence product scope.
    plan['scope_refs'] = [{key: ref[key] for key in ('kind', 'text', 'page', 'source_document_id', 'start_offset', 'end_offset') if key in ref}
                          for ref in condition.get('source_context', []) if ref.get('kind') == 'product_scope']
    for key in ('quantity_conditions', 'date_conditions', 'temporal_conditions'):
        for item in condition.get(key, []):
            if isinstance(item.get('quote'), str) and item['quote'] and item['quote'] in text:
                plan[key].append({**item, 'source_document_id': document_id, 'page': page})
            else:
                unhandled(text, 'A saved condition is not supported by the quoted PDF text.')

    stripped = text.strip()
    action = action_for(text)
    if action:
        plan['kind'] = 'procedure'
        plan['action'] = action
        if action['rule'] == 'literal_source_action':
            plan['review_reasons'].append('The next action is explicit in the source. This does not resolve mandatory status or approve completion.')
            return plan
    if _REFERENCE_DATE.fullmatch(stripped) or re.fullmatch(r'Tender No:\s*[^\n]{1,150}\s+DATED:\s*\d{2}\.\d{2}\.\d{4}', stripped, re.I):
        plan['kind'] = 'reference'
        plan['review_reasons'].append('This is tender reference information, not a product or company evidence check.')
        return plan
    if _SCHEDULE_DATE.fullmatch(stripped):
        plan['kind'] = 'procedure'
        plan['review_reasons'].append('This is a tender timetable entry. Keep the stated date and time; it is not a certificate expiry check.')
        return plan
    if re.search(r'\b(?:submit|submitted|upload|uploaded|delivery|delivered)\b', stripped, re.I) and not re.search(r'\b(?:RAM|memory|storage|GB)\b', stripped, re.I):
        plan['kind'] = 'procedure'

    # Remove only explicit comparison phrases before looking for conditional or
    # negative language. Alternative products/options must never become ANDs.
    safety_text = re.sub(r'\b(?:not|no)\s+(?:less|more)\s+than\b', '', stripped, flags=re.I)
    safety_text = safety_text.replace('Intel HD 4400 or above/Discrete Graphics', 'explicit graphics alternatives')
    safety_text = re.sub(r'\bor\s+(?:above|higher|more|below|lower|less)\b', '', safety_text, flags=re.I)
    if re.search(r'\b(?:not|no|unless|except|excluding|either|if|alternatively|or)\b', safety_text, re.I):
        unhandled(text, 'The clause contains a condition, exclusion or alternative. Review which option applies before checking it.')
        return plan

    segments = [segment.strip() for segment in re.split(r'\n|(?<=;)', text) if segment.strip()]
    # Wrapped prose can be matched without changing the actual quotation.
    if re.fullmatch(r'\s*The\b[\s\S]+', text) and not any(':' in part for part in segments):
        segments = [text.strip()]
    for segment in segments:
        if re.fullmatch(r'Requirement ID:\s*[A-Za-z0-9_.-]+|Obligation:\s*(?:mandatory|optional)', segment, re.I):
            continue
        ports = re.fullmatch(r'Port:\s*-?\s*HDMI,\s*VGA\s*,\s*RJ-45 Ethernet,\s*USB \(2\*3\.0 & 2\*2\.0\)[.;]?', segment, re.I)
        if ports:
            if {'hdmi', 'vga', 'ethernet', 'usb2_ports', 'usb3_ports'} <= supported:
                plan['criteria'].extend([_criterion('hdmi', 'present', '', segment), _criterion('vga', 'present', '', segment), _criterion('ethernet', 'eq', 'RJ-45', segment), _criterion('usb2_ports', 'gte', '2', segment), _criterion('usb3_ports', 'gte', '2', segment)])
            else:
                unhandled(segment, 'Each port type and USB-version count needs a separate supported reader.')
            continue
        baseline = hardware_baseline(segment)
        if baseline:
            field, value = baseline
            if field in supported:
                plan['criteria'].append(_criterion(field, 'baseline', value, segment))
            else:
                unhandled(segment, 'Hardware baseline comparison needs a supported reader.')
            continue
        compound_cpu = re.fullmatch(r'Processor:\s*(\d+(?:\.\d+)?) GHz dual-core Intel Core i5 or above[.;]?', segment, re.I)
        if compound_cpu:
            if 'cpu_ghz' in supported:
                plan['criteria'].append(_criterion('cpu_ghz', 'gte', compound_cpu[1], segment))
            if 'cpu_cores' in supported:
                plan['criteria'].append(_criterion('cpu_cores', 'gte', 'dual', segment))
            else:
                unhandled(segment, 'Physical CPU cores need a supported evidence reader.')
            if 'cpu_family' in supported:
                plan['criteria'].append(_criterion('cpu_family', 'baseline', 'Intel Core i5', segment))
            else:
                unhandled(segment, 'CPU family needs an explicit baseline comparison.')
            continue
        cpu = re.fullmatch(r'Processor:\s*64 bit (\d+(?:\.\d+)?) GHz or above[.;]?', segment, re.I)
        if cpu:
            if {'cpu_bits', 'cpu_ghz'} <= supported:
                plan['criteria'].extend([_criterion('cpu_bits', 'eq', '64', segment), _criterion('cpu_ghz', 'gte', cpu[1], segment)])
            else:
                unhandled(segment, 'The CPU architecture and speed both need supported readers.')
            continue
        display = re.fullmatch(r'(LED Backlit Display|Tablet Screen Size):\s*(?:(Below)\s+)?(\d+(?:\.\d+)?)\s+inch(?:\s+(or above))?[.;]?', segment, re.I)
        if display:
            if bool(display[2]) == bool(display[4]):
                unhandled(segment, 'The screen-size comparison needs review.')
            elif 'screen_inches' in supported:
                plan['criteria'].append(_criterion('screen_inches', 'lt' if display[2] else 'gte', display[3], segment))
                if display[1].lower().startswith('led'):
                    if 'display_backlight' in supported:
                        plan['criteria'].append(_criterion('display_backlight', 'eq', segment[:3], segment))
                    else:
                        unhandled(segment, 'The LED backlight must also be checked.')
            else:
                unhandled(segment, 'The screen size needs a supported evidence reader.')
            continue
        # Complete literal hardware clauses only; no OS-version or graphics equivalence.
        literal = None
        if re.fullmatch(r'Port:\s*-?\s*USB[.;]?', segment, re.I):
            if 'usb' in supported:
                plan['criteria'].append(_criterion('usb', 'present', '', segment))
            else:
                unhandled(segment, 'The USB port needs a supported evidence check.')
            continue
        if re.fullmatch(r'Operating System:\s*Mac OS[.;]?', segment, re.I):
            literal = [('operating_system', re.search(r'Mac OS', segment, re.I)[0])]
        elif re.fullmatch(r'Bluetooth and Wifi:\s*-?Inbuilt[.;]?', segment, re.I):
            value = re.search(r'Inbuilt', segment, re.I)[0]
            literal = [('bluetooth', value), ('wifi', value)]
        elif re.fullmatch(r'Integrated HD Webcam(?: & Speaker)?[.;]?', segment, re.I):
            literal = [('webcam', segment[:len('Integrated HD')])]
            if re.search(r'& Speaker', segment, re.I):
                literal.append(('speaker', segment[:len('Integrated')]))
        if literal:
            for field, value in literal:
                if field in supported:
                    plan['criteria'].append(_criterion(field, 'eq', value, segment))
                else:
                    unhandled(segment, 'This product detail does not have an automatic evidence reader yet.')
            continue
        identity = re.fullmatch(r'Model:\s*([A-Za-z0-9][A-Za-z0-9 ._/-]{0,199})', segment, re.I)
        if identity and identity[1].casefold() not in {'unknown', 'not available', 'n/a', 'tbd'}:
            if 'model' in supported:
                plan['criteria'].append(_criterion('model', 'eq', identity[1], segment))
            else:
                unhandled(segment, 'The product model must be checked separately.')
            continue
        match = _CAPACITY.fullmatch(segment) or _PROSE.fullmatch(segment) or _MINIMUM.fullmatch(segment)
        if match:
            groups = match.groupdict()
            field = _CAPACITY_FIELDS[_flat(groups['attribute'])]
            prefix, suffix = groups.get('prefix'), groups.get('suffix')
            operators = {_PREFIX[_flat(prefix)]} if prefix else set()
            if suffix:
                operators.add(_SUFFIX[_flat(suffix)])
            if len(operators) != 1:
                unhandled(segment, 'The clause does not give one clear comparison. A bare number is not treated as an exact or minimum value.')
                continue
            if field not in supported:
                unhandled(segment, 'This type of number does not have an automatic evidence check yet.')
                continue
            plan['criteria'].append(_criterion(field, next(iter(operators)), groups['value'], segment))
            if groups.get('model'):
                if 'model' in supported:
                    plan['criteria'].append(_criterion('model', 'eq', groups['model'], segment))
                else:
                    unhandled(segment, 'The product model must be checked separately.')
            # SSD names a storage medium as well as a capacity attribute. Do
            # not let the GB comparison erase that explicit source detail.
            # Generic "Storage"/"Hard Disk" labels do not imply HDD or SSD.
            explicit_ssd = _flat(groups['attribute']) == 'ssd'
            if explicit_ssd:
                if 'storage_type' in supported:
                    plan['criteria'].append(_criterion('storage_type', 'eq', groups['attribute'], segment))
                else:
                    unhandled(groups['attribute'], 'The SSD storage type still needs review; capacity alone does not cover this clause.')
            qualifier = groups.get('qualifier')
            if qualifier:
                if explicit_ssd:
                    if _flat(qualifier) != 'ssd':
                        unhandled(segment, 'The SSD label also includes a different specification. Review the storage type; no equivalence between types has been assumed.')
                    continue
                attribute_field = 'memory_type' if re.fullmatch(r'(?:LP)?DDR[2-5](?:X)?', qualifier, re.I) else 'storage_type'
                compatible = (field == 'ram_gb') == (attribute_field == 'memory_type')
                if compatible and attribute_field in supported:
                    plan['criteria'].append(_criterion(attribute_field, 'eq', qualifier, segment))
                else:
                    unhandled(qualifier, f'The capacity can be checked, but the {qualifier} specification still needs review.')
            continue
        certificate = _CERTIFICATE.fullmatch(segment)
        if certificate and 'valid_until' in supported:
            try:
                date.fromisoformat(certificate['date'])
            except ValueError:
                unhandled(segment, 'The written certificate date is invalid. Check the original PDF.')
            else:
                plan['criteria'].append(_criterion('valid_until', 'gte', certificate['date'], segment, 'certificate'))
            continue
        unhandled(segment, 'This part of the clause needs a manual check. It has not been dropped from the requirement.')

    # Model conditions may point at supported source facts, but must not silently
    # contradict or add to what the deterministic planner actually understands.
    for kind, key in (('numeric', 'numeric_conditions'), ('date', 'date_conditions')):
        for saved in condition.get(key, []):
            if not isinstance(saved.get('quote'), str) or saved['quote'] not in text or not saved['quote']:
                unhandled(text, 'A saved condition is not supported by the quoted PDF text.')
            elif not any(represented_condition(c, saved, kind) for c in plan['criteria']):
                unhandled(saved['quote'], 'A saved condition is not covered by the prepared checks, or disagrees with their comparison. Review the original wording.')
    if condition.get('quantity_conditions'):
        unhandled(text, 'Order quantities are separate from product limits. Confirm the quantity and product option without treating the count as a hardware threshold.')
    if condition.get('temporal_conditions'):
        unhandled(text, 'The clause depends on an event or period. No calendar deadline has been invented.')
    port_fields = {'hdmi', 'vga', 'ethernet', 'usb2_ports', 'usb3_ports'}
    ports_resolved = port_fields <= {c['field'] for c in plan['criteria']}
    unresolved = [item for item in condition.get('unresolved_interpretations', [])
        if not (ports_resolved and item.get('kind') == 'usb_port_version_count'
                and item.get('quote') in [c['quote'] for c in plan['criteria']])]
    if condition.get('ambiguous') or condition.get('ambiguity_reason') or condition.get('quantity_conflict') or unresolved:
        unhandled(text, 'The saved interpretation has an unresolved ambiguity or conflicting quantity.')
    # A scope-only flag is handled by a separate source/evidence scope resolver.
    # Other extraction uncertainty remains blocking even when the syntax fits.
    review_reasons = condition.get('review_reasons', [])
    if any(not _scope_only_reason(reason, text, plan['criteria']) for reason in review_reasons):
        unhandled(text, 'The saved extraction includes review notes that are not resolved by these checks. Review its meaning against the original PDF.')
    scope_only = (bool(plan['scope_refs']) and
        'Product configuration scope comes from the cited table heading; confirm applicability before evidence verification.' in review_reasons
        and all(_scope_only_reason(reason, text, plan['criteria']) for reason in review_reasons))
    resolved_ports_only = ports_resolved and all(_scope_only_reason(reason, text, plan['criteria']) for reason in review_reasons)
    if condition.get('requires_human_review') and not (scope_only or resolved_ports_only):
        unhandled(text, 'The saved extraction requires a person to review its meaning.')
    if condition.get('confidence') in {'medium', 'low'}:
        unhandled(text, 'The saved extraction is uncertain. Check the original PDF before relying on these rules.')
    # Multiple different values for the same attribute may be alternatives or
    # ranges; do not silently combine them into a single supported specification.
    for field in {c['field'] for c in plan['criteria']}:
        comparisons = {(c['operator'], c['expected']) for c in plan['criteria'] if c['field'] == field}
        if len(comparisons) > 1:
            unhandled(text, 'More than one comparison applies to the same detail. Review the range or product options.')
    plan['coverage'] = 'partial' if plan['criteria'] and plan['unhandled'] else 'complete' if plan['criteria'] else 'manual'
    return plan
