"""Conservative verification of explicitly labelled facts, never similarity-as-proof.

Rule coverage is deliberately bounded. Complete literal clauses can be checked
automatically; unparsed text and ambiguous identity remain reviewable. Final
human approval is separate from a document-based result.
"""
import re
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Literal
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from .models import (Workspace, DocumentVersion, SourceSpan, RequirementVersion, EvidenceFact,
                     EvidenceLibraryEntry, Assessment, AssessmentEvidence, ReviewDecision, CorrectiveTask,
                     AssessmentDependency, ReassessmentImpact)
from .check_planning import DEFAULT_FIELDS, build_check_plan, represented_condition
from .product_scope import scope_evidence
from .hardware_comparison import baseline_match
from . import component_dependencies

RULES_VERSION = 'source_scoped_checks_v10'

EvidenceType = Literal['datasheet', 'authorization', 'certificate', 'project_reference']
Status = Literal['supported', 'missing', 'conflicting', 'outdated', 'inconclusive']
LABELS = {'supported': 'Supported by evidence', 'missing': 'Missing', 'conflicting': 'Conflict detected',
          'outdated': 'Outdated', 'inconclusive': 'Needs human review'}
FIELD_LABELS = {'model': 'Model', 'bidder': 'Bidder', 'ram_gb': 'RAM', 'storage_gb': 'Storage',
                'valid_until': 'Valid until', 'valid_from': 'Valid from', 'project_value_inr': 'Project value',
                'certificate_number': 'Certificate number', 'manufacturer': 'Manufacturer',
                'project_reference': 'Project reference', 'storage_type': 'Storage type', 'memory_type': 'Memory type', 'operating_system': 'Operating System', 'bluetooth': 'Bluetooth', 'wifi': 'Wifi', 'webcam': 'Webcam', 'speaker': 'Speaker', 'usb': 'USB', 'screen_inches': 'Screen size', 'display_backlight': 'Display backlight', 'cpu_ghz': 'CPU speed', 'cpu_bits': 'CPU architecture', 'cpu_cores': 'CPU cores', 'cpu_family': 'CPU family', 'processor': 'Processor', 'graphics': 'Graphics', 'hdmi': 'HDMI', 'vga': 'VGA', 'ethernet': 'Ethernet', 'usb2_ports': 'USB 2.0 ports', 'usb3_ports': 'USB 3.0 ports'}
NUMBER_FIELDS = {'ram_gb', 'storage_gb', 'project_value_inr', 'screen_inches', 'cpu_ghz', 'cpu_bits', 'cpu_cores', 'usb2_ports', 'usb3_ports'}


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, str_strip_whitespace=True)


class Criterion(Strict):
    field: Literal['model','bidder','ram_gb','storage_gb','valid_until','valid_from','project_value_inr','certificate_number','manufacturer','project_reference','storage_type','memory_type','operating_system','bluetooth','wifi','webcam','speaker','usb','screen_inches','display_backlight','cpu_ghz','cpu_bits','cpu_cores','cpu_family','processor','graphics','hdmi','vga','ethernet','usb2_ports','usb3_ports']
    operator: Literal['eq', 'gte', 'lte', 'lt', 'present', 'baseline']
    expected: str = Field(max_length=200)
    quote: str = Field(min_length=1, max_length=5000)
    evidence_type: EvidenceType

    @model_validator(mode='after')
    def valid_comparison(self):
        compatible = {
            'model': {'datasheet','authorization'}, 'ram_gb': {'datasheet'}, 'storage_gb': {'datasheet'},
            'storage_type': {'datasheet'}, 'memory_type': {'datasheet'},
            **{field: {'datasheet'} for field in ('operating_system','bluetooth','wifi','webcam','speaker','usb','screen_inches','display_backlight','cpu_ghz','cpu_bits','cpu_cores','cpu_family','processor','graphics','hdmi','vga','ethernet','usb2_ports','usb3_ports')},
            'bidder': {'authorization','certificate','project_reference'},
            'certificate_number': {'certificate'}, 'project_value_inr': {'project_reference'},
            'project_reference': {'project_reference'},
        }
        if self.field in compatible and self.evidence_type not in compatible[self.field]:
            raise ValueError('This field cannot be verified using that evidence type')
        if self.operator != 'present' and not self.expected:
            raise ValueError('A comparison needs an expected value')
        if self.field not in NUMBER_FIELDS | {'valid_until','valid_from'} and self.operator not in {'eq','present','baseline'}:
            raise ValueError('Text fields support equality or presence only')
        if self.operator == 'baseline' and self.field not in {'cpu_family','processor','graphics'}:
            raise ValueError('Baseline matching is restricted to hardware identity fields')
        return self


class VerifyInput(Strict):
    criteria: list[Criterion] = Field(default_factory=list, max_length=30)
    coverage_confirmed: bool = False
    reviewer: str = Field(default='', max_length=200)

    @model_validator(mode='after')
    def reviewer_needed(self):
        if self.coverage_confirmed and not self.reviewer:
            raise ValueError('A named reviewer must confirm complete criterion coverage')
        return self


class ReviewInput(Strict):
    action: Literal['approved','rejected','reopened','corrected']
    reviewer: str = Field(min_length=1, max_length=200)
    comment: str = Field(min_length=1, max_length=4000)
    corrected_status: Status | None = None

    @model_validator(mode='after')
    def correction(self):
        if (self.action == 'corrected') != (self.corrected_status is not None):
            raise ValueError('Only corrections require a replacement status')
        return self


class ManualRequirement(Strict):
    page: int = Field(ge=1)
    excerpt: str = Field(min_length=1, max_length=5000)
    reviewer: str = Field(min_length=1, max_length=200)


def normalize(value):
    return ' '.join(value.casefold().split())


def typed(field, value):
    if field == 'cpu_cores':
        if normalize(value) in {'dual', 'dual-core'}:
            return Decimal(2)
        match = re.fullmatch(r'(\d+)(?:\s*cores?)?', value.strip(), re.I)
        if not match or int(match[1]) < 1:
            raise ValueError('Physical core count must be a positive whole number')
        return Decimal(match[1])
    if field in {'cpu_ghz', 'cpu_bits'}:
        unit = 'GHz' if field == 'cpu_ghz' else 'bit'
        match = re.fullmatch(r'(\d+(?:\.\d+)?)(?:\s*' + unit + r')?', value.strip(), re.I)
        if not match:
            raise ValueError('Explicit CPU value required')
        return Decimal(match[1])
    if field == 'screen_inches':
        match = re.fullmatch(r'(\d+(?:\.\d+)?)(?:\s*inches|\s*inch)?', value.strip(), re.I)
        if not match:
            raise ValueError('Screen size requires inches')
        return Decimal(match[1])
    if field in {'usb2_ports', 'usb3_ports'}:
        match = re.fullmatch(r'(\d+)(?:\s*ports?)?', value.strip(), re.I)
        if not match:
            raise ValueError('Port count must be a whole number')
        return Decimal(match[1])
    if field in {'usb', 'hdmi', 'vga'}:
        if normalize(value) not in {'yes', 'present', 'included', field}:
            raise ValueError('USB presence is not explicitly established')
        return 'present'
    if field in NUMBER_FIELDS:
        pattern = r'(?:INR\s*)?([0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?)(?:\s*GB)?'
        match = re.fullmatch(pattern, value.strip(), re.I)
        if not match:
            raise ValueError('Unsupported numeric unit or range')
        if field in {'ram_gb','storage_gb'} and 'INR' in value.upper():
            raise ValueError('Wrong unit')
        if field == 'project_value_inr' and 'GB' in value.upper():
            raise ValueError('Wrong unit')
        return Decimal(match[1].replace(',', ''))
    if field in {'valid_until', 'valid_from'}:
        return date.fromisoformat(value)
    return normalize(value)


def read_facts(span):
    facts = []
    # Anchor complete lines, so a heading, negated prose, or a semantic hit cannot
    # become a field value. Tables and unlabeled prose intentionally abstain.
    labels = [(field, label) for field, label in FIELD_LABELS.items()]
    labels.extend([('ram_gb', 'Memory'), ('storage_gb', 'Hard Disk')])
    for field, label in labels:
        for match in re.finditer(r'^\s*' + re.escape(label) + r':\s*([^\n\r]+)$', span.text, re.M | re.I):
            raw = match[1].strip()
            quote = match[0].strip()
            # A complete, explicit capacity/type phrase yields two linked facts;
            # do not strip arbitrary trailing claims or alternative values.
            qualifier = None
            if field in {'ram_gb', 'storage_gb'}:
                kinds = r'(?:(?:LP)?DDR[2-5]X?)' if field == 'ram_gb' else r'(?:Flash|SSD|HDD)'
                measured = re.fullmatch(r'([\d,.]+\s*GB)(?:\s+(' + kinds + r'))?', raw, re.I)
                if measured:
                    raw = measured[1]
                    qualifier = measured[2]
            try:
                if normalize(raw) in {'', '-', 'n/a', 'na', 'none', 'no', 'unknown', 'pending', 'not provided', 'not available', 'not applicable', 'missing', 'tbd'}:
                    raise ValueError('Placeholder is not supporting evidence')
                if field in {'ram_gb','storage_gb'} and not re.fullmatch(r'[\d,.]+\s*GB', raw, re.I):
                    raise ValueError('GB unit required')
                if field in {'cpu_ghz', 'cpu_bits'} and not re.fullmatch(r'\d+(?:\.\d+)?\s*' + ('GHz' if field == 'cpu_ghz' else 'bit'), raw, re.I):
                    raise ValueError('Explicit CPU unit required')
                if field in {'usb2_ports', 'usb3_ports'} and not re.fullmatch(r'\d+(?:\s*ports?)?', raw, re.I):
                    raise ValueError('Port count must be a whole number')
                if field == 'screen_inches' and not re.fullmatch(r'\d+(?:\.\d+)?\s*inch(?:es)?', raw, re.I):
                    raise ValueError('Explicit inch unit required')
                if field == 'project_value_inr' and not raw.upper().startswith('INR '):
                    raise ValueError('INR unit required')
                value = typed(field, raw)
                parsed = str(value)
            except (ValueError, InvalidOperation):
                parsed = None
            facts.append({'field': field, 'raw_value': raw, 'normalized': {
                'value': parsed, 'quote': quote, 'method': 'deterministic_label_parser_v1',
                'source_span_id': span.id, 'page': span.page, 'document_version_id': span.document_version_id,
                'authenticity': 'not_independently_verified'}})
            if qualifier:
                facts.append({'field': 'memory_type' if field == 'ram_gb' else 'storage_type',
                    'raw_value': qualifier, 'normalized': {'value': normalize(qualifier), 'quote': quote,
                    'method': 'deterministic_capacity_type_v1', 'source_span_id': span.id,
                    'page': span.page, 'document_version_id': span.document_version_id,
                    'authenticity': 'not_independently_verified'}})
    return facts


def require_requirement(db, wid, rid):
    req = db.scalar(select(RequirementVersion).where(RequirementVersion.workspace_id == wid, RequirementVersion.id == rid))
    if req is None:
        raise HTTPException(404, 'Requirement not found in this workspace.')
    return req


def condition_criterion(req, condition, kind):
    """Translate only source-explicit conditions whose meaning is unambiguous.

    The model output selects a candidate, but the field, comparison, value and
    unit must also be established by the requirement text itself.
    """
    quote = condition.get('quote', '')
    if not isinstance(quote, str) or not quote or quote not in req.statement:
        return None
    if kind == 'date':
        boundary = condition.get('boundary_text', '')
        if (condition.get('relation') != 'valid_through' or not isinstance(boundary, str) or not boundary or
            not re.search(r'\bcertificate\b', req.statement, re.I) or
            re.search(r'\b(?:not|no|unless|except|excluding|or)\b', req.statement, re.I) or
            not re.search(r'\bvalid\s+through\s+' + re.escape(boundary) + r'\b', quote, re.I)):
            return None
        try:
            typed('valid_until', boundary)
        except ValueError:
            return None
        return {'field': 'valid_until', 'operator': 'gte', 'expected': boundary,
                'quote': quote, 'evidence_type': 'certificate'}

    value, unit, operator = condition.get('value_text'), condition.get('unit_text'), condition.get('operator')
    if not isinstance(value, str) or not isinstance(unit, str) or value not in quote:
        return None
    # Some models preserve the measured attribute inside unit_text ("GB RAM").
    # Keep that raw extraction intact; accept only this bounded source-backed
    # form, and check the attribute against the independently parsed clause.
    unit_match = re.fullmatch(r'GB(?:\s+(RAM|memory|storage|SSD))?', unit, re.I)
    if not unit_match or (unit_match.group(1) and unit not in quote):
        return None
    value_match = re.fullmatch(r'([0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?)(?:\s*GB)?', value.strip(), re.I)
    if not value_match:
        return None
    number = value_match.group(1)
    # Use the complete requirement if the model quoted just the number. Restrict
    # this fallback to a single numeric condition and a single GB quantity.
    text = quote
    fields = [('ram_gb', r'\b(?:RAM|memory)\b'), ('storage_gb', r'\b(?:storage|SSD)\b')]
    cues = {'>=': r'(?:at least|minimum|not less than|no less than)',
            '<=': r'(?:at most|maximum|not more than|no more than)'}
    if operator not in cues:
        return None
    if (not any(re.search(pattern, text, re.I) for _, pattern in fields) or
        not re.search(r'\b' + cues[operator] + r'\b', text, re.I)):
        if len(req.condition.get('numeric_conditions', [])) != 1 or len(req.statement) > 5000:
            return None
        text = req.statement
    matches = [field for field, pattern in fields if re.search(pattern, text, re.I)]
    if len(matches) != 1 or len(re.findall(r'\b[0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?\s*GB\b', text, re.I)) != 1:
        return None
    if unit_match.group(1):
        unit_field = 'ram_gb' if unit_match.group(1).casefold() in {'ram', 'memory'} else 'storage_gb'
        if unit_field != matches[0]:
            return None
    # Reject negation and conditional/alternative clauses we cannot interpret.
    # A model may quote only the positive-looking fragment of a negated or
    # conditional sentence; inspect the complete clause before suggesting a rule.
    stripped = re.sub(r'\b(?:not|no)\s+(?:less|more)\s+than\b', '', req.statement, flags=re.I)
    if re.search(r'\b(?:not|no|unless|except|excluding|or)\b', stripped, re.I):
        return None
    quantity = re.escape(number) + r'\s*GB\b'
    field_pattern = next(pattern for field, pattern in fields if field == matches[0])
    cue = r'\b' + cues[operator] + r'\b'
    patterns = [cue + r'\s*(?:(?:of|is)\s+)?' + quantity + r'\s*(?:of\s+)?' + field_pattern,
                cue + r'\s+' + field_pattern + r'\s*(?:(?:is|of)\s*|:\s*)?' + quantity,
                field_pattern + r'\s*(?:(?:must|shall|should)\s+be\s+|(?:is|of)\s*)?' + cue + r'\s*(?:(?:is|of)\s*|:\s*)?' + quantity]
    if not any(re.search(pattern, text, re.I) for pattern in patterns):
        return None
    return {'field': matches[0], 'operator': 'gte' if operator == '>=' else 'lte',
            'expected': value, 'quote': text, 'evidence_type': 'datasheet'}


def threshold_sentence(req):
    """Recognize a complete, single-condition sentence, not a similarity match.

    The model condition must agree with independently parsed source wording.
    The returned key masks only the capacity, preserving model, operator and
    every other word. Unknown prose deliberately has no automatic identity.
    """
    condition = req.condition
    if (getattr(req, 'obligation', None) != 'mandatory' or condition.get('confidence') != 'high'
        or getattr(req, 'category', None) == 'manual_review'
        or condition.get('date_conditions') or len(condition.get('numeric_conditions', [])) != 1
        or condition.get('ambiguous') or condition.get('requires_human_review')
        or any(c.get('kind') == 'product_scope' for c in condition.get('source_context', []))
        or any(re.search(r'\b(ambiguous|uncertain|uncertainty|unsupported|incomplete|conflicting|contradictory)\b', reason, re.I)
               for reason in condition.get('review_reasons', []))):
        return None
    match = re.fullmatch(
        r'The\s+(?:(?P<model>[A-Za-z0-9]+(?:[ -][A-Za-z0-9]+){0,7})\s+)?product\s+'
        r'(?:must|shall)\s+have\s+(?P<comparison>at least|at most)\s+'
        r'(?P<value>[0-9]+(?:\.[0-9]+)?)\s+GB\s+(?P<attribute>RAM|memory|storage|SSD)\.?',
        req.statement.strip(), re.I)
    if not match or re.search(r'\b(or|and|not|no|unless|except|if|equivalent)\b', req.statement, re.I):
        return None
    candidate = condition_criterion(req, condition['numeric_conditions'][0], 'numeric')
    field = 'ram_gb' if match['attribute'].lower() in {'ram', 'memory'} else 'storage_gb'
    operator = 'gte' if match['comparison'].lower() == 'at least' else 'lte'
    if (candidate is None or candidate['field'] != field or candidate['operator'] != operator
        or typed(field, candidate['expected']) != typed(field, match['value'])):
        return None
    criteria = [candidate]
    if match['model']:
        criteria.append({'field': 'model', 'operator': 'eq', 'expected': match['model'],
                         'quote': match['model'], 'evidence_type': 'datasheet'})
    statement = req.statement.strip()
    key = normalize(statement[:match.start('value')] + '<capacity>' + statement[match.end('value'):]).rstrip('.')
    return {'key': key, 'criteria': criteria}


def _propose_candidates(req):
    result = []
    # Suggestions only. Human coverage confirmation is still mandatory.
    for field in ('model','bidder','ram_gb','storage_gb','valid_until','project_value_inr','certificate_number'):
        label = FIELD_LABELS[field]
        for match in re.finditer(r'^' + re.escape(label) + r':\s*(?:(at least|at most)\s+)?([^\n]+)$', req.statement, re.M | re.I):
            value = match[2].strip()
            result.append({'field': field, 'operator': 'gte' if match[1] and match[1].lower() == 'at least' else 'lte' if match[1] else 'eq',
                'expected': value, 'quote': match[0], 'evidence_type': 'datasheet' if field in {'model','ram_gb','storage_gb'} else 'project_reference' if field == 'project_value_inr' else 'certificate' if field == 'certificate_number' else 'authorization'})
    # AI conditions are suggestions, not authoritative rules. Only map a narrow
    # grammar whose field, unit, operator and value are explicit in the clause.
    for kind, key in [('numeric', 'numeric_conditions'), ('date', 'date_conditions')]:
        for condition in req.condition.get(key, []):
            candidate = condition_criterion(req, condition, kind)
            if candidate and not any(c['field'] == candidate['field'] and c['operator'] == candidate['operator']
                                     and c['expected'] == candidate['expected'] for c in result):
                result.append(candidate)
    sentence = threshold_sentence(req)
    if sentence:
        # This complete sentence supplies product identity as well as capacity.
        # Full evidence coverage and final approval remain separate decisions.
        return sentence['criteria']
    return result


def automatic_proposals(req):
    """Only expose runnable suggestions; unsupported wording remains a finding.

    Labelled PDF rows can contain suffixes, alternate values or several product
    attributes. Never coerce these into equality checks by stripping the extra
    words. Explicit user criteria still go through verify's strict validation.
    """
    criteria, review_reasons = [], []
    for candidate in _propose_candidates(req):
        try:
            criterion = Criterion(**candidate)
            if criterion.quote not in req.statement:
                raise ValueError('Missing source wording')
            if criterion.operator != 'present':
                if normalize(criterion.expected) not in normalize(criterion.quote):
                    raise ValueError('Missing source value')
                typed(criterion.field, criterion.expected)
        except (ValueError, InvalidOperation):
            field = FIELD_LABELS.get(candidate.get('field'), 'Requirement')
            review_reasons.append(f'{field}: the wording cannot be safely turned into an automatic check. Review the value, unit and comparison in the original PDF.')
            continue
        criteria.append(criterion.model_dump())
    return criteria, list(dict.fromkeys(review_reasons))


def propose(req):
    return automatic_proposals(req)[0]


def list_evidence(db, wid, include_superseded=False):
    rows = db.execute(select(DocumentVersion, EvidenceLibraryEntry).join(EvidenceLibraryEntry,
        EvidenceLibraryEntry.document_version_id == DocumentVersion.id).where(DocumentVersion.workspace_id == wid)
        .order_by(DocumentVersion.created_at, DocumentVersion.id)).all()
    superseded = {doc.supersedes_id for doc, _ in rows if doc.supersedes_id}
    return rows if include_superseded else [(doc, entry) for doc, entry in rows if doc.id not in superseded]


def _criterion_key(item):
    values = item.model_dump() if isinstance(item, Criterion) else item
    expected = typed(values['field'], values['expected']) if values['operator'] != 'present' else ''
    return values['field'], values['operator'], str(expected), values['evidence_type']


def prepared_verification(db, req):
    """Build a source-grounded plan and explicit evidence assignment, without AI."""
    source = db.get(SourceSpan, req.source_span_id)
    plan = build_check_plan(req, source, supported_fields=DEFAULT_FIELDS | {'storage_type', 'memory_type', 'operating_system', 'bluetooth', 'wifi', 'webcam', 'speaker', 'usb', 'screen_inches', 'display_backlight', 'cpu_ghz', 'cpu_bits', 'cpu_cores', 'cpu_family', 'processor', 'graphics', 'hdmi', 'vga', 'ethernet', 'usb2_ports', 'usb3_ports'})
    plan['dependencies'] = component_dependencies.components(db, req)
    plan['source_criteria'] = list(plan['criteria'])
    # Preserve existing supported API values/quotes when their meaning agrees.
    legacy, legacy_reasons = automatic_proposals(req)
    criteria = list(plan['criteria'])
    for old in legacy:
        equal = next((i for i, item in enumerate(criteria) if _criterion_key(item) == _criterion_key(old)), None)
        if equal is not None:
            criteria[equal] = old
        elif not any(item['field'] == old['field'] for item in criteria):
            criteria.append(old)
    for item in criteria:
        Criterion(**item)
        if item['quote'] not in source.text or item['quote'] not in req.statement:
            raise HTTPException(422, 'Prepared checks must match the original source page exactly.')
    plan['criteria'] = criteria
    if not plan['criteria']:
        plan['coverage'] = 'manual'
    # The new planner has parsed these fields without discarding qualifiers.
    # Retain old-parser warnings only for wording not handled by the plan.
    covered_labels = {FIELD_LABELS[item['field']] for item in plan['criteria']}
    plan['review_reasons'] = list(dict.fromkeys([*plan['review_reasons'],
        *(reason for reason in legacy_reasons if reason.split(':', 1)[0] not in covered_labels)]))
    spans_by_doc, by_doc = {}, {}
    for doc, entry in list_evidence(db, req.workspace_id):
        spans = list(db.scalars(select(SourceSpan).where(SourceSpan.workspace_id == req.workspace_id,
            SourceSpan.document_version_id == doc.id)))
        spans_by_doc[doc.id] = spans
        by_doc[doc.id] = (doc, entry, [fact for span in spans for fact in read_facts(span)])
    source_ids = {source.document_version_id, *(c.get('source_document_id') for c in req.condition.get('source_context', []))} - {None}
    requirement_spans = list(db.scalars(select(SourceSpan).where(SourceSpan.workspace_id == req.workspace_id,
        SourceSpan.document_version_id.in_(source_ids))))
    mapping = scope_evidence(req, by_doc, spans_by_doc, requirement_spans)
    plan['scope'] = mapping['summary']
    plan['auto_coverage_eligible'] = (plan['coverage'] == 'complete' and bool(criteria)
        and not plan['review_reasons'] and mapping['required_scope']['state'] != 'needs_review')
    return plan, mapping, by_doc


def verification_preview(db, req):
    plan, _, _ = prepared_verification(db, req)
    return plan


def _manually_covered_line(text, criteria):
    """Keep named, explicit legacy checks usable without hiding extra wording.

    This is only called after a reviewer confirms coverage. It accepts a whole
    labelled value/presence line, never arbitrary prose or a partial quotation.
    """
    for criterion in criteria:
        label = FIELD_LABELS[criterion.field]
        match = re.fullmatch(re.escape(label) + r':\s*(.+)', text, re.I)
        if not match or text not in criterion.quote:
            continue
        value = match[1].strip()
        if criterion.operator == 'present':
            if normalize(value) == 'must be present':
                return True
            continue
        prefix = re.fullmatch(r'(at least|at most)\s+(.+)', value, re.I)
        if prefix:
            if criterion.operator != ('gte' if prefix[1].lower() == 'at least' else 'lte'):
                continue
            value = prefix[2]
        # Exact full values keep extra qualifiers/alternatives from disappearing.
        if normalize(value) == normalize(criterion.expected):
            return True
    return False


def planning_update_needed(db, req, assessment):
    """Upgrade unreviewed automatic findings, preserving reviewed/custom history."""
    if any(check.get('method') == 'human_correction' for check in assessment.checks):
        return False
    if db.scalar(select(ReviewDecision.id).where(ReviewDecision.assessment_id == assessment.id).limit(1)):
        return False
    context = next((c for c in assessment.checks if c.get('method') == 'verification_context'), {})
    if context.get('rules_version') == RULES_VERSION or context.get('reviewer') or context.get('coverage_confirmed'):
        return False
    # Do not replace previous custom criteria. Empty old checks are safely
    # upgradeable, and an old grammar-generated set must still match exactly.
    old = context.get('criteria', [])
    previous_plan = context.get('check_plan', {})
    generated_before = (str(context.get('rules_version', '')).startswith('source_scoped_checks_')
        and old == previous_plan.get('criteria') and old == previous_plan.get('source_criteria'))
    if old and old != propose(req) and not generated_before:
        return False
    plan = verification_preview(db, req)
    old_dependencies = {d['requirement_id'] for d in previous_plan.get('dependencies', [])}
    if {d['requirement_id'] for d in plan.get('dependencies', [])} != old_dependencies:
        return True
    return bool(plan['criteria']) and (plan['criteria'] != old or (not context.get('automatic_coverage') and plan['auto_coverage_eligible']))


def verify(db, wid, rid, payload, *, commit=True, reuse=None, affected_fields=None, infer_criteria=True):
    workspace = db.scalar(select(Workspace).where(Workspace.id == wid).with_for_update())
    req = require_requirement(db, wid, rid)
    if req.condition.get('disposition') in {'reference', 'duplicate'}:
        raise HTTPException(422, 'Reference-only text is not a supplier compliance requirement.')
    if db.scalar(select(RequirementVersion.id).where(RequirementVersion.workspace_id == wid, RequirementVersion.supersedes_id == req.id).limit(1)):
        raise HTTPException(409, 'This interpretation was superseded. Verify its current revision.')
    plan, mapping, all_docs = prepared_verification(db, req)
    automatic_review_reasons = list(plan['review_reasons']) if infer_criteria else []
    proposed = plan['criteria'] if infer_criteria else []
    if payload.criteria:
        criteria = payload.criteria
    elif infer_criteria:
        criteria = [Criterion(**item) for item in proposed]
    else:
        criteria = []
    if payload.coverage_confirmed:
        for reason in tuple(automatic_review_reasons):
            parts = [item for item in plan['unhandled'] if item['reason'] == reason]
            if (reason == 'This part of the clause needs a manual check. It has not been dropped from the requirement.'
                    and parts and all(_manually_covered_line(item['text'], criteria) for item in parts)):
                automatic_review_reasons.remove(reason)
    source = db.get(SourceSpan, req.source_span_id)
    for criterion in criteria:
        if criterion.quote not in req.statement or criterion.quote not in source.text:
            raise HTTPException(422, 'Criterion quotation must occur exactly in this requirement and its source.')
        if criterion.operator != 'present':
            if normalize(criterion.expected) not in normalize(criterion.quote):
                raise HTTPException(422, 'Expected value must occur in the criterion quotation.')
            try:
                typed(criterion.field, criterion.expected)
            except (ValueError, InvalidOperation):
                raise HTTPException(422, 'Unsupported expected value. Use explicit GB, INR, or ISO date values.') from None
    by_doc = mapping['by_doc']
    same_prepared = {_criterion_key(c) for c in criteria} == {_criterion_key(c) for c in proposed}
    automatic_coverage = infer_criteria and same_prepared and plan['auto_coverage_eligible']
    checks = [{'method': 'verification_context', 'rules_version': RULES_VERSION,
               'criteria': [c.model_dump() for c in criteria], 'coverage_confirmed': payload.coverage_confirmed,
               'automatic_coverage': automatic_coverage, 'check_plan': plan,
               'reviewer': payload.reviewer, 'requirement_provenance': req.condition.get('provenance', 'model_or_legacy_extraction'), 'evaluated_on': datetime.now(timezone.utc).date().isoformat(),
               'library_document_ids': list(all_docs), 'officially_verified': False}]
    linked = {}
    reused_fact_ids = set()
    if reuse is not None and affected_fields is not None:
        for prior in reuse.checks:
            if prior.get('method') == 'deterministic' and prior.get('field') not in affected_fields and prior.get('field') != 'coverage':
                checks.append({**prior, 'execution': 'reused', 'reused_from_assessment_id': reuse.id})
                reused_fact_ids.update(ref['fact_id'] for ref in prior.get('sources', []))
    def should_run(field):
        return affected_fields is None or field in affected_fields or field == 'coverage'
    def check(field, outcome, rationale, facts=(), document_id=None):
        refs = []
        for fact in facts:
            key = (fact['normalized']['source_span_id'], fact['field'], fact['raw_value'])
            if key not in linked:
                row = EvidenceFact(workspace_id=wid, source_span_id=key[0], **fact)
                db.add(row); db.flush(); linked[key] = row
            row = linked[key]
            refs.append({'fact_id': row.id, **fact['normalized'], 'raw_value': row.raw_value,
                         'filename': all_docs[fact['normalized']['document_version_id']][0].filename})
        checks.append({'method': 'deterministic', 'execution': 'executed', 'field': field, 'outcome': outcome,
                       'rationale': rationale, 'document_id': document_id, 'sources': refs})
    # The UI sends suggested criteria back as explicit input. Editing or
    # confirming those valid checks must not erase an unsupported part of the
    # original clause. A reviewer can explicitly correct the final result with
    # a comment; that separate, audited decision is not a deterministic pass.
    for rationale in automatic_review_reasons:
        check('interpretation', 'review', rationale)
    if req.condition.get('requires_human_review') and not automatic_coverage and not any(c.get('kind') == 'product_scope' for c in req.condition.get('source_context', [])):
        check('interpretation', 'review', 'This extraction has unresolved interpretation issues. Review and correct its source-backed criteria before relying on evidence checks.')
    for item in mapping['checks']:
        check('product_scope', item['outcome'], item['rationale'], item['facts'], item['document_id'])
    if not criteria:
        check('coverage', 'review', 'No supported check specification. Review the requirement and define source-backed criteria.')
    if not payload.coverage_confirmed and not automatic_coverage:
        check('coverage', 'review', 'A human must confirm that these criteria cover the entire requirement, including document purpose and scope.')
    elif automatic_coverage:
        check('coverage', 'pass', 'All details in this bounded clause have source-backed automatic checks. This is not a human approval.')
    supplied_keys = {_criterion_key(c) for c in criteria}
    for expected_check in plan['source_criteria']:
        if _criterion_key(expected_check) not in supplied_keys:
            check('coverage', 'review', f'The source requires a {FIELD_LABELS[expected_check["field"]]} check that was omitted or changed. Restore the prepared check, or record an explicit reviewer correction.')
    for kind, key in [('numeric', 'numeric_conditions'), ('date', 'date_conditions')]:
        for condition in req.condition.get(key, []):
            candidate = condition_criterion(req, condition, kind)
            represented = candidate and any(c.field == candidate['field'] and c.operator == candidate['operator']
                and c.evidence_type == candidate['evidence_type']
                and typed(c.field, c.expected) == typed(candidate['field'], candidate['expected']) for c in criteria)
            # A complete plan independently reconciles every extracted condition
            # with the full source clause, including supported suffix comparisons.
            represented = represented or any(represented_condition(c.model_dump(), condition, kind) for c in criteria)
            if not represented:
                check('coverage', 'review', 'An extracted condition has no corresponding source-backed check; review and add a suitable criterion.')
    models = {normalize(c.expected) for c in criteria if c.field == 'model' and c.operator == 'eq'}
    for criterion in criteria:
        if not should_run(criterion.field):
            continue
        candidates = [(doc, entry, facts) for doc, entry, facts in by_doc.values() if entry.evidence_type == criterion.evidence_type]
        if not candidates:
            if mapping['requires_review'] and criterion.evidence_type in {'datasheet', 'authorization'}:
                check(criterion.field, 'review', 'Company documents exist but their product assignment is unclear; no value was selected automatically.')
            else:
                check(criterion.field, 'missing', f'No {criterion.evidence_type} document is available for this requirement and product option.')
        for doc, entry, facts in candidates:
            values = [f for f in facts if f['field'] == criterion.field]
            if not values:
                check(criterion.field, 'review', f'{doc.filename}: required field is not extractable; absence of a parsed field does not prove absence in the PDF.', document_id=doc.id)
                continue
            if any(f['normalized']['value'] is None for f in values):
                check(criterion.field, 'review', 'Unsupported units, date format, or ambiguous value.', values, doc.id)
                continue
            actual = {typed(criterion.field, f['raw_value']) for f in values}
            if len(actual) != 1:
                check(criterion.field, 'conflict', 'The document gives conflicting values for the same field; no value was selected silently.', values, doc.id)
                continue
            actual_value = next(iter(actual))
            expected = typed(criterion.field, criterion.expected) if criterion.operator != 'present' else None
            if criterion.operator == 'baseline':
                matched = baseline_match(actual_value, expected)
                check(criterion.field, 'pass' if matched else 'review',
                    f'{doc.filename}: observed {values[0]["raw_value"]}; source baseline {criterion.expected}. ' +
                    ('Exact source-declared baseline/alternative matched; no performance ranking inferred.' if matched else 'A different CPU/GPU needs documented equivalence; model-number magnitude is not proof of performance.'), values, doc.id)
                continue
            passed = criterion.operator == 'present' or {'eq': lambda: actual_value == expected,
                'gte': lambda: actual_value >= expected, 'lte': lambda: actual_value <= expected, 'lt': lambda: actual_value < expected}[criterion.operator]()
            outcome = 'pass' if passed else 'outdated' if criterion.field in {'valid_until','valid_from'} else 'conflict'
            check(criterion.field, outcome, f'{doc.filename}: {criterion.field} {criterion.operator} {criterion.expected or "present"}; observed {values[0]["raw_value"]}.', values, doc.id)
    # Identity and temporal guards apply to every document considered, never to
    # detached numeric facts mixed across different product documents.
    considered = {c.evidence_type for c in criteria}
    for doc, entry, facts in by_doc.values():
        if entry.evidence_type not in considered:
            continue
        if should_run('bidder_identity') and entry.evidence_type in {'authorization','certificate','project_reference'}:
            bidders = [f for f in facts if f['field'] == 'bidder']
            if not bidders:
                check('bidder_identity', 'review', 'No explicit bidder field; legal-entity scope needs review.', document_id=doc.id)
            else:
                good = all(normalize(f['raw_value']) == normalize(workspace.supplier_name) for f in bidders)
                check('bidder_identity', 'pass' if good else 'conflict', 'Exact legal-name comparison to the workspace supplier (case and whitespace normalized only).', bidders, doc.id)
        if should_run('product_scope') and entry.evidence_type in {'datasheet','authorization'}:
            found = [f for f in facts if f['field'] == 'model']
            if mapping['matched'] and mapping['required_scope']['key'] and found and not models:
                check('product_scope', 'pass', 'The document names one model under the matching tender configuration; only that configuration\'s facts are used.', found, doc.id)
            elif len(models) != 1 or not found:
                check('product_scope', 'review', 'Expected product/model identity is not unambiguously established for this requirement.', found, doc.id)
            else:
                good = all(normalize(f['raw_value']) in models for f in found)
                check('product_scope', 'pass' if good else 'conflict', 'Product facts are checked within the same document and exact model scope.', found, doc.id)
        for fact in [f for f in facts if should_run('validity') and f['field'] in {'valid_until','valid_from'}]:
            if fact['normalized']['value'] is None:
                check('validity', 'review', 'Unparseable date requires review.', [fact], doc.id)
                continue
            value = date.fromisoformat(fact['normalized']['value'])
            today = datetime.now(timezone.utc).date()
            stale = value < today if fact['field'] == 'valid_until' else value > today
            check('validity', 'outdated' if stale else 'pass', f'Document {fact["field"]} compared with assessment date {today.isoformat()}.', [fact], doc.id)
    # Contradictory datasheets for the same exact product must not be combined
    # or cherry-picked, even when both numbers individually meet a minimum.
    for field in {c.field for c in criteria if c.evidence_type == 'datasheet'} & NUMBER_FIELDS:
        if not should_run(field):
            continue
        grouped = {}
        for doc, entry, facts in by_doc.values():
            if entry.evidence_type != 'datasheet':
                continue
            identities = {normalize(f['raw_value']) for f in facts if f['field'] == 'model'}
            if len(identities) == 1:
                grouped.setdefault(next(iter(identities)), []).extend(f for f in facts if f['field'] == field and f['normalized']['value'] is not None)
        for identity, facts in grouped.items():
            if len({f['normalized']['document_version_id'] for f in facts}) > 1 and len({f['normalized']['value'] for f in facts}) > 1:
                check(field, 'conflict', f'Datasheets disagree for model {identity}; configuration or revision scope needs human resolution.', facts)
    for dependency in plan.get('dependencies', []):
        child = db.get(Assessment, dependency['assessment_id']) if dependency['assessment_id'] else None
        view = assessment_view(db, child) if child else None
        outcome = 'pass' if view and not view['stale'] and view['status'] == 'supported' and view['review_state'] not in {'rejected','reopened'} else 'review'
        checks.append({'method': 'component_dependency', 'field': 'component', 'outcome': outcome,
            **dependency, 'sources': [], 'rationale': 'Component clause on page ' + str(dependency['page']) + ': ' + dependency['quote'] + ('. Its current evidence assessment is supported; this does not approve the combined clause.' if outcome == 'pass' else '. Check or reassess this component; its current result cannot support the combined clause.')})
    outcomes = {c.get('outcome') for c in checks}
    status = next((s for outcome, s in [('conflict','conflicting'), ('outdated','outdated'), ('missing','missing'), ('review','inconclusive')] if outcome in outcomes), 'supported')
    checks[0]['display_status'] = status
    assessment = Assessment(workspace_id=wid, requirement_version_id=rid, workspace_revision=workspace.revision,
        status='inconclusive' if status == 'outdated' else status, checks=checks,
        explanation=f'{LABELS[status]}. Document-based checks only; authenticity and official verification have not been established.')
    db.add(assessment); db.flush()
    for fact in linked.values():
        db.add(AssessmentEvidence(workspace_id=wid, assessment_id=assessment.id, evidence_fact_id=fact.id))
    for fact_id in reused_fact_ids:
        db.add(AssessmentEvidence(workspace_id=wid, assessment_id=assessment.id, evidence_fact_id=fact_id))
    db.flush()
    record_dependencies(db, assessment)
    if status != 'supported':
        db.add(CorrectiveTask(workspace_id=wid, assessment_id=assessment.id,
            title=f'Resolve evidence finding: {LABELS[status]}', explanation='\n'.join(c['rationale'] for c in checks if c.get('outcome') not in {None,'pass','not_applicable'}) + '\nObtain evidence addressing these discrepancies, upload the replacement document, and rerun the requirement checks. Then request human review.'))
    if commit:
        db.commit()
    else:
        db.flush()
    return assessment_view(db, assessment)


def assessment_view(db, row):
    context = row.checks[0] if row.checks else {}
    reviews = db.scalars(select(ReviewDecision).where(ReviewDecision.assessment_id == row.id).order_by(ReviewDecision.created_at, ReviewDecision.id)).all()
    workspace = db.get(Workspace, row.workspace_id)
    evaluated_on = next((c.get('evaluated_on') for c in row.checks if c.get('evaluated_on')), None)
    verification_context = next((c for c in row.checks if c.get('method') == 'verification_context'), {})
    if 'library_document_ids' in verification_context:
        categories = {c['evidence_type'] for c in verification_context.get('criteria', [])}
        old_ids = set(verification_context['library_document_ids'])
        relevant_ids = {d.id for d, e in list_evidence(db, row.workspace_id) if e.evidence_type in categories}
        # Documents are append-only; only the evidence categories actually used
        # can invalidate the assessment. Tender uploads are not evidence changes.
        # Detect both added and superseded evidence, within relevant categories.
        all_rows = list_evidence(db, row.workspace_id, include_superseded=True)
        old_relevant = {d.id for d, e in all_rows if d.id in old_ids and e.evidence_type in categories}
        evidence_changed = relevant_ids != old_relevant
    else:
        evidence_changed = row.workspace_revision != workspace.revision
    temporal = not verification_context.get('criteria') or any(
        c.get('field') in {'validity','valid_until','valid_from'} for c in row.checks)
    invalidated = db.scalar(select(ReassessmentImpact.id).where(ReassessmentImpact.old_assessment_id == row.id).limit(1)) is not None
    corrected = any(r.condition.get('reconciliation_version') and not r.condition.get('canonicalized_from')
        for r in db.scalars(select(RequirementVersion).where(RequirementVersion.workspace_id == row.workspace_id,
            RequirementVersion.supersedes_id == row.requirement_version_id)))
    dependency_changed = component_dependencies.changed(db, row)
    stale = dependency_changed or evidence_changed or invalidated or corrected or (temporal and evaluated_on is not None and evaluated_on != datetime.now(timezone.utc).date().isoformat())
    tasks = db.scalars(select(CorrectiveTask).where(CorrectiveTask.assessment_id == row.id)).all()
    return {'id': row.id, 'requirement_id': row.requirement_version_id,
        'status': context.get('display_status', row.status),
        'label': LABELS[context.get('display_status', row.status)], 'explanation': row.explanation,
        'checks': row.checks, 'created_at': row.created_at.isoformat(),
        'workspace_revision': row.workspace_revision, 'stale': stale, 'review_state': reviews[-1].action if reviews else 'awaiting_review',
        'officially_verified': False, 'requires_reassessment': invalidated or corrected or dependency_changed,
        'dependency_changed': dependency_changed,
        'reviews': [{'id': r.id, 'action': r.action, 'reviewer': r.reviewer, 'comment': r.comment, 'created_at': r.created_at.isoformat()} for r in reviews],
        'tasks': [{'id': t.id, 'title': t.title, 'explanation': t.explanation, 'status': t.status} for t in tasks]}


def review(db, wid, aid, payload):
    workspace = db.scalar(select(Workspace).where(Workspace.id == wid).with_for_update())
    original = db.scalar(select(Assessment).where(Assessment.workspace_id == wid, Assessment.id == aid))
    if original is None:
        raise HTTPException(404, 'Assessment not found in this workspace.')
    if payload.action in {'approved','corrected'} and assessment_view(db, original)['stale']:
        raise HTTPException(409, 'Evidence or the assessment date changed since this assessment. Rerun verification before approving or correcting.')
    latest = db.scalar(select(Assessment).where(Assessment.workspace_id == wid,
        Assessment.requirement_version_id == original.requirement_version_id)
        .order_by(Assessment.created_at.desc(), Assessment.id.desc()).limit(1))
    if payload.action in {'approved','corrected'} and latest.id != original.id:
        raise HTTPException(409, 'A newer assessment exists. Review the latest assessment instead.')
    target = original
    if payload.action == 'corrected':
        checks = [{'method': 'human_correction', 'display_status': payload.corrected_status,
            'supersedes_assessment_id': original.id, 'reviewer': payload.reviewer, 'rationale': payload.comment,
            'officially_verified': False}, *original.checks]
        target = Assessment(workspace_id=wid, requirement_version_id=original.requirement_version_id,
            workspace_revision=workspace.revision, status='inconclusive' if payload.corrected_status == 'outdated' else payload.corrected_status,
            explanation='Human correction: ' + payload.comment, checks=checks)
        db.add(target); db.flush()
        for link in db.scalars(select(AssessmentEvidence).where(AssessmentEvidence.assessment_id == original.id)):
            db.add(AssessmentEvidence(workspace_id=wid, assessment_id=target.id, evidence_fact_id=link.evidence_fact_id))
        db.flush()
        record_dependencies(db, target)
        db.flush()  # Freeze links only after the replacement is fully assembled.
        db.add(ReviewDecision(workspace_id=wid, assessment_id=original.id, action='reopened',
            reviewer=payload.reviewer, comment=f'Correction recorded in {target.id}: {payload.comment}', workspace_revision=workspace.revision))
    db.add(ReviewDecision(workspace_id=wid, assessment_id=target.id,
        action='approved' if payload.action == 'corrected' else payload.action,
        reviewer=payload.reviewer, comment=payload.comment, workspace_revision=workspace.revision))
    db.commit()
    return assessment_view(db, target)


def record_dependencies(db, assessment):
    """Materialize field/product/fact dependencies without editing any history."""
    if db.scalar(select(AssessmentDependency.id).where(AssessmentDependency.assessment_id == assessment.id).limit(1)):
        return
    context = next((c for c in assessment.checks if c.get('method') == 'verification_context'), {})
    product = next((c['expected'] for c in context.get('criteria', []) if c['field'] == 'model'), None)
    for check in assessment.checks:
        if check.get('method') != 'deterministic':
            continue
        for fact_id in {s['fact_id'] for s in check.get('sources', [])} or {None}:
            db.add(AssessmentDependency(workspace_id=assessment.workspace_id, assessment_id=assessment.id,
                requirement_version_id=assessment.requirement_version_id, evidence_fact_id=fact_id,
                field=check['field'], product_model=product))
