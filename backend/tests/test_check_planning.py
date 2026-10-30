"""Source-grounded planning; these tests never call a provider or live database."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from tenderready.check_planning import DEFAULT_FIELDS, build_check_plan, represented_condition


def inputs(text, condition=None):
    req = SimpleNamespace(statement=text, condition=condition or {}, source_span_id='span-1',
                          workspace_id='workspace-1', obligation='mandatory')
    span = SimpleNamespace(id='span-1', workspace_id='workspace-1', document_version_id='document-1',
                           page=2, text='Annexure\n' + text + '\nOther clause')
    return req, span


def numeric(text, value, operator='>=', unit='GB', **extra):
    return {'numeric_conditions': [{'quote': text, 'value_text': value,
                                    'operator': operator, 'unit_text': unit}], **extra}


@pytest.mark.parametrize(('text', 'field', 'operator', 'expected'), [
    ('Memory: 4 GB or above', 'ram_gb', 'gte', '4'),
    ('Memory: 8 GB or below;', 'ram_gb', 'lte', '8'),
    ('Hard Disk: 500 GB or above;', 'storage_gb', 'gte', '500'),
    ('Storage: 16 GB or Higher;', 'storage_gb', 'gte', '16'),
    ('Memory: 2GB or higher;', 'ram_gb', 'gte', '2'),
    ('RAM: at least 32 GB', 'ram_gb', 'gte', '32'),
    ('RAM: no less than 32 GB', 'ram_gb', 'gte', '32'),
    ('Memory: not more than 8 GB', 'ram_gb', 'lte', '8'),
    ('RAM: exactly 32 GB.', 'ram_gb', 'eq', '32'),
    ('The product must have at least 32 GB RAM.', 'ram_gb', 'gte', '32'),
    ('The minimum RAM is 32 GB.', 'ram_gb', 'gte', '32'),
    ('The maximum memory is 8 GB.', 'ram_gb', 'lte', '8'),
])
def test_clear_whole_clause_has_exact_source_and_comparison(text, field, operator, expected):
    raw_operator = {'gte': '>=', 'lte': '<=', 'eq': '='}[operator]
    req, span = inputs(text, numeric(text, expected, raw_operator))
    before = deepcopy(req.condition)
    plan = build_check_plan(req, span)
    assert plan['coverage'] == 'complete'
    assert plan['criteria'] == [{'field': field, 'operator': operator, 'expected': expected,
                                'quote': text, 'evidence_type': 'datasheet'}]
    assert plan['sources'] == [{'source_document_id': 'document-1', 'source_span_id': 'span-1',
                                'page': 2, 'quote': text}]
    assert not plan['unhandled']
    assert req.condition == before


@pytest.mark.parametrize(('text', 'field', 'qualifier'), [
    ('Storage: 128 GB Flash or above', 'storage_type', 'Flash'),
    ('Storage: 512 GB SSD or above', 'storage_type', 'SSD'),
    ('Storage: 500 GB HDD or above', 'storage_type', 'HDD'),
    ('Memory: 4 GB DDR3 or higher', 'memory_type', 'DDR3'),
    ('Memory: 4 GB LPDDR3 or higher', 'memory_type', 'LPDDR3'),
])
def test_type_qualifier_requires_matching_evidence_reader_capability(text, field, qualifier):
    req, span = inputs(text)
    capacity_only = build_check_plan(req, span)
    assert capacity_only['coverage'] == 'partial'
    assert len(capacity_only['criteria']) == 1
    assert capacity_only['unhandled'][0]['text'] == qualifier
    full = build_check_plan(req, span, supported_fields=DEFAULT_FIELDS | {field})
    assert full['coverage'] == 'complete'
    assert full['criteria'][1] == {'field': field, 'operator': 'eq', 'expected': qualifier,
                                  'quote': text, 'evidence_type': 'datasheet'}


@pytest.mark.parametrize('text', [
    'SSD: at least 128 GB', 'SSD: 128 GB or above',
    'The product must have at least 128 GB SSD.', 'The minimum SSD is 128 GB.',
    'SSD: 128 GB SSD or above',
])
def test_ssd_attribute_is_a_required_source_type_not_just_gb(text):
    req, span = inputs(text, numeric(text, '128'))
    capacity_only = build_check_plan(req, span)
    assert capacity_only['coverage'] == 'partial'
    assert len(capacity_only['criteria']) == 1
    complete = build_check_plan(req, span, supported_fields=DEFAULT_FIELDS | {'storage_type'})
    assert complete['coverage'] == 'complete'
    assert [(c['field'], c['operator'], c['expected']) for c in complete['criteria']] == [
        ('storage_gb', 'gte', '128'), ('storage_type', 'eq', 'SSD')]
    assert all(c['quote'] == text for c in complete['criteria'])
    assert complete['sources'][0]['page'] == 2


@pytest.mark.parametrize('qualifier', ['HDD', 'Flash', 'DDR3'])
def test_different_ssd_qualifier_remains_unresolved(qualifier):
    text = f'SSD: 128 GB {qualifier} or above'
    plan = build_check_plan(*inputs(text), supported_fields=DEFAULT_FIELDS | {'storage_type', 'memory_type'})
    assert plan['coverage'] == 'partial'
    assert any(c['field'] == 'storage_type' and c['expected'] == 'SSD' for c in plan['criteria'])
    assert any('no equivalence' in reason for reason in plan['review_reasons'])


def test_generic_hard_disk_label_does_not_infer_hdd():
    plan = build_check_plan(*inputs('Hard Disk: 500 GB or above'), supported_fields=DEFAULT_FIELDS | {'storage_type'})
    assert plan['coverage'] == 'complete'
    assert [c['field'] for c in plan['criteria']] == ['storage_gb']


@pytest.mark.parametrize(('storage', 'status'), [('128 GB HDD', 'conflicting'),
                                                ('128 GB SSD', 'supported'), ('128 GB', 'inconclusive')])
def test_ssd_tender_checks_real_evidence_type_not_capacity_alone(database, tmp_path, storage, status):
    from test_batch_verification import client_for, store_requirements
    from test_documents import workspace
    from test_verification import pdf, send_pdf
    engine, sessions = database
    with client_for(engine, tmp_path) as client:
        wid = workspace(client)
        _, ids = store_requirements(client, sessions, wid, [('Model: Atlas A14\nSSD: at least 128 GB', {})])
        evidence = send_pdf(client, wid, pdf(f'Model: Atlas A14\nStorage: {storage}'), 'datasheet')
        response = client.post(f'/workspaces/{wid}/requirements/{ids[0]}/verify', json={})
        assert response.status_code == 201, response.text
        result = response.json()
        assert result['status'] == status and result['review_state'] == 'awaiting_review'
        assert not result['officially_verified']
        assert any(c.get('field') == 'storage_gb' and c.get('outcome') == 'pass' for c in result['checks'])
        kind = next(c for c in result['checks'] if c.get('field') == 'storage_type')
        assert kind['outcome'] == {'conflicting': 'conflict', 'supported': 'pass', 'inconclusive': 'review'}[status]
        if kind['sources']:
            assert kind['sources'][0]['quote'] == f'Storage: {storage}'
            assert kind['sources'][0]['document_version_id'] == evidence['id']


@pytest.mark.parametrize('text', [
    'RAM: 16 GB',  # No invented exactness or minimum.
    'RAM: at least 4 TB',
    'RAM: at least 32',
    'RAM: at least 32 MB',
    'RAM: at least 32 GB or below',
    'RAM: at least 32 GB or storage: at least 512 GB',
    'RAM: at least 32 GB unless a tablet is offered',
    'RAM must not be at least 32 GB',
    'Either RAM: at least 16 GB or RAM: at least 32 GB',
    'If a laptop is supplied, RAM: at least 32 GB',
    'RAM: not at least 32 GB',
    'Order quantity: at least 32 units',
    'Display: 13.3 inches or above',
    'Processor: i5 or equivalent',
])
def test_unsupported_units_options_negations_and_quantities_abstain(text):
    plan = build_check_plan(*inputs(text))
    assert plan['coverage'] == 'manual'
    assert plan['criteria'] == []
    assert plan['review_reasons']


def test_mixed_clause_keeps_unhandled_text_instead_of_partial_false_support():
    text = 'Model: Acme M1\nMemory: 4 GB DDR3 or higher\nProcessor: i5 or equivalent'
    plan = build_check_plan(*inputs(text))
    assert plan['coverage'] == 'manual'  # The alternative makes the whole clause unsafe.
    assert not plan['criteria']
    text = 'Model: Acme M1\nMemory: 4 GB DDR3 or higher\nWarranty: three years'
    plan = build_check_plan(*inputs(text))
    assert plan['coverage'] == 'partial'
    assert {rule['field'] for rule in plan['criteria']} == {'model', 'ram_gb'}
    assert {item['text'] for item in plan['unhandled']} == {'DDR3', 'Warranty: three years'}


@pytest.mark.parametrize('change', [
    {'operator': '<='}, {'operator': '>'}, {'value_text': '16'}, {'unit_text': 'GB storage'},
    {'unit_text': 'MB'}, {'quote': 'RAM: at least 64 GB'}, {'value_text': None},
])
def test_contradictory_cached_condition_never_gets_complete_coverage(change):
    text = 'RAM: at least 32 GB'
    condition = numeric(text, '32')
    condition['numeric_conditions'][0].update(change)
    plan = build_check_plan(*inputs(text, condition))
    assert plan['coverage'] == 'partial'
    assert plan['criteria'][0]['expected'] == '32'
    assert plan['review_reasons']


def test_unrepresented_second_condition_and_same_field_ranges_require_review():
    text = 'RAM: at least 32 GB'
    condition = numeric(text, '32')
    condition['numeric_conditions'].append({**condition['numeric_conditions'][0], 'operator': '<='})
    assert build_check_plan(*inputs(text, condition))['coverage'] == 'partial'
    ranged = 'RAM: at least 16 GB\nRAM: at most 32 GB'
    assert build_check_plan(*inputs(ranged))['coverage'] == 'partial'


@pytest.mark.parametrize('flag', [
    {'ambiguous': True}, {'ambiguity_reason': 'Two possible products'},
    {'requires_human_review': True}, {'confidence': 'medium'}, {'confidence': 'low'},
    {'unresolved_interpretations': ['which product?']},
])
def test_saved_ambiguity_survives_syntactically_clear_plan(flag):
    plan = build_check_plan(*inputs('Memory: 4 GB or above', flag))
    assert plan['coverage'] == 'partial'
    assert plan['criteria']


@pytest.mark.parametrize('flag', [False, None])
@pytest.mark.parametrize('note', [
    'Ambiguous product interpretation', 'The comparison is not clear.',
    'Unknown configuration applicability', 'Check whether a different option applies.',
    'Cached model fixture needs review.',
])
def test_review_notes_cannot_be_lost_when_review_boolean_is_missing_or_false(flag, note):
    text = 'Memory: 4 GB or above'
    condition = numeric(text, '4', confidence='high', review_reasons=[note])
    if flag is not None:
        condition['requires_human_review'] = flag
    plan = build_check_plan(*inputs(text, condition))
    assert plan['coverage'] == 'partial'
    assert plan['criteria'][0]['expected'] == '4'
    assert any('review notes' in reason for reason in plan['review_reasons'])


@pytest.mark.parametrize('note', [
    'Manually transcribed; no model extraction claimed.',
    'Limited labelled grammar; completeness requires reviewer confirmation.',
])
def test_known_extraction_provenance_does_not_hide_real_residual_clause_text(note):
    req, span = inputs('RAM: at least 32 GB', {'review_reasons': [note]})
    assert build_check_plan(req, span)['coverage'] == 'complete'
    req, span = inputs('RAM: at least 32 GB\nWarranty: onsite support', {'review_reasons': [note]})
    assert build_check_plan(req, span)['coverage'] == 'partial'


def test_known_scope_only_review_flags_are_deferred_to_scope_resolver():
    text = 'Memory: 4 GB or above'
    context = {'kind': 'product_scope', 'text': 'Configuration A', 'page': 2,
               'source_document_id': 'document-1', 'start_offset': 20, 'end_offset': 35}
    condition = numeric(text, '4', source_context=[context], confidence='high', requires_human_review=True,
                        review_reasons=['Specifies minimum memory requirement: 4 GB or above',
                                        'Explicit obligation wording could not be validated.',
                                        'Product configuration scope comes from the cited table heading; confirm applicability before evidence verification.'])
    req, span = inputs(text, condition)
    req.obligation = 'unclear'
    plan = build_check_plan(req, span)
    assert plan['coverage'] == 'complete'  # Only rule coverage, never identity/readiness/approval.
    assert plan['scope_refs'] == [context]
    assert req.obligation == 'unclear'
    condition['review_reasons'].append('The meaning is unclear even after reading the source.')
    assert build_check_plan(req, span)['coverage'] == 'partial'
    condition['review_reasons'] = []
    assert build_check_plan(req, span)['coverage'] == 'partial'


@pytest.mark.parametrize(('text', 'note'), [
    ('Memory: 8 GB or below;', 'Explicit maximum memory specification'),
    ('Hard Disk: 500 GB or above;', 'Explicit minimum hard disk capacity'),
    ('Storage: 16 GB or Higher;', "Explicit minimum storage requirement with 'or Higher' phrasing"),
    ('Memory: 2GB or higher;', "Explicit minimum memory (RAM) requirement with 'or higher' phrasing"),
])
def test_cached_mea_positive_notes_do_not_turn_scope_flags_into_meaning_ambiguity(text, note):
    condition = {'requires_human_review': True,
                 'source_context': [{'kind': 'product_scope', 'text': 'Configuration A', 'page': 2}],
                 'review_reasons': [note, 'Explicit obligation wording could not be validated.',
                                   'Product configuration scope comes from the cited table heading; confirm applicability before evidence verification.']}
    req, span = inputs(text, condition)
    assert build_check_plan(req, span)['coverage'] == 'complete'
    condition['review_reasons'][0] = note.replace('minimum', 'maximum') if 'minimum' in note else note.replace('maximum', 'minimum')
    assert build_check_plan(req, span)['coverage'] == 'partial'


@pytest.mark.parametrize(('text', 'kind'), [
    ('Published Date 01.09.2015 (2000 hrs)', 'reference'),
    ('Date of Technical Bid Opening (online) 22.09.2015 (1530 hrs)', 'reference'),
    ('Tender No: Q/Comp/885/45/2015 DATED: 01.09.2015', 'reference'),
    ('Bid Document Download Start Date 02.09.2015 (0900 hrs)', 'procedure'),
    ('Bid Submission End Date (online) 21.09.2015 (1730 hrs)', 'procedure'),
    ('Clarification End Date 16.09.2015 (1730 hrs)', 'procedure'),
    ('The bid shall be submitted online only. Manual bids shall not be accepted.', 'procedure'),
])
def test_metadata_and_timetable_do_not_become_certificate_expiry_checks(text, kind):
    condition = {'date_conditions': [{'quote': text, 'relation': 'on', 'boundary_text': '21.09.2015'}]}
    plan = build_check_plan(*inputs(text, condition))
    assert plan['kind'] == kind
    assert plan['coverage'] == 'manual'
    assert not plan['criteria']
    assert plan['date_conditions'][0]['quote'] == text
    assert plan['date_conditions'][0]['page'] == 2


def test_explicit_certificate_validity_is_distinct_from_event_based_deadline():
    text = 'The certificate must be valid through 2026-12-31.'
    condition = {'date_conditions': [{'quote': text, 'relation': 'valid_through', 'boundary_text': '2026-12-31'}]}
    plan = build_check_plan(*inputs(text, condition))
    assert plan['coverage'] == 'complete'
    assert plan['criteria'][0]['field'] == 'valid_until'
    condition['date_conditions'][0]['relation'] = 'before'
    assert build_check_plan(*inputs(text, condition))['coverage'] == 'partial'
    text = 'Delivery shall be completed within 30 days of the order.'
    condition = {'temporal_conditions': [{'quote': text, 'event': 'order'}]}
    event_plan = build_check_plan(*inputs(text, condition))
    assert event_plan['coverage'] == 'manual'
    assert not event_plan['criteria']
    assert event_plan['temporal_conditions'][0]['quote'] == text
    assert build_check_plan(*inputs('Certificate valid through 2026-02-30'))['coverage'] == 'manual'


def test_quantity_never_becomes_gb_and_is_preserved_with_page_reference():
    text = 'Memory: 4 GB or above'
    condition = {'quantity_conditions': [{'quote': text, 'value_text': '4', 'unit_text': 'units'}]}
    plan = build_check_plan(*inputs(text, condition))
    assert plan['coverage'] == 'partial'
    assert plan['criteria'][0]['field'] == 'ram_gb'
    assert plan['quantity_conditions'][0]['page'] == 2


@pytest.mark.parametrize(('target', 'field', 'value'), [
    ('req', 'source_span_id', 'another-span'), ('req', 'workspace_id', 'another-workspace'),
    ('span', 'text', 'Different requirement'), ('span', 'page', 0), ('span', 'page', True),
    ('span', 'document_version_id', None), ('span', 'id', None),
])
def test_original_source_and_workspace_links_are_required(target, field, value):
    req, span = inputs('RAM: at least 32 GB')
    setattr(req if target == 'req' else span, field, value)
    plan = build_check_plan(req, span)
    assert plan['coverage'] == 'manual'
    assert not plan['criteria']


def test_32gb_rule_uses_existing_typed_comparison_and_rejects_16gb_fact():
    # Integration at the existing deterministic field reader boundary. Parent
    # tests exercise the persisted assessment/API path with the same plan.
    from tenderready.verification import Criterion, read_facts, typed
    text = 'The product must have at least 32 GB RAM.'
    plan = build_check_plan(*inputs(text, numeric(text, '32')))
    rule = Criterion.model_validate(plan['criteria'][0])
    evidence = SimpleNamespace(id='evidence-span', page=1, document_version_id='evidence-document', text='RAM: 16 GB')
    fact = read_facts(evidence)[0]
    assert fact['field'] == rule.field
    assert typed(rule.field, fact['raw_value']) < typed(rule.field, rule.expected)
    assert rule.operator == 'gte'
    assert represented_condition(rule.model_dump(), numeric(text, '32')['numeric_conditions'][0])
    assert fact['normalized']['page'] == 1
    assert plan['sources'][0]['page'] == 2


def test_known_usb_mapping_is_resolved_without_mutating_cached_uncertainty():
 text='Port:- HDMI, VGA ,RJ-45 Ethernet, USB (2*3.0 & 2*2.0)'
 condition={'requires_human_review':True, 'review_reasons':[
  'USB version identifiers are not numerical measurement units. Original port specification is retained; count/version mapping needs review.'],
  'unresolved_interpretations':[{'kind':'usb_port_version_count','quote':text}]}
 req,span=inputs(text,condition)
 before=deepcopy(req.condition)
 fields={'hdmi','vga','ethernet','usb2_ports','usb3_ports'}
 plan=build_check_plan(req,span,supported_fields=fields)
 assert plan['coverage']=='complete' and not plan['review_reasons']
 assert req.condition==before
 req.condition={**condition,'ambiguous':True}
 assert build_check_plan(req,span,supported_fields=fields)['coverage']=='partial'
 req.condition={**condition,'unresolved_interpretations':[{'kind':'other','quote':text}]}
 assert build_check_plan(req,span,supported_fields=fields)['coverage']=='partial'


def test_positive_usb_extraction_note_is_not_an_unresolved_condition():
 req,span=inputs('Port:- USB',{'review_reasons':['Specifies port requirement: USB']})
 plan=build_check_plan(req,span,supported_fields={'usb'})
 assert plan['coverage']=='complete' and not plan['review_reasons']
 req.condition['review_reasons'].append('USB compatibility is uncertain')
 assert build_check_plan(req,span,supported_fields={'usb'})['coverage']=='partial'


@pytest.mark.parametrize('value,unit,operator,matched', [
 ('5th Generation',None,'>=',True), ('5','generation','>=',True),
 ('4th Generation',None,'>=',False), ('5',None,'>=',False),
 ('5th Generation','GHz','>=',False), ('5th Generation',None,'<=',False),
])
def test_cpu_generation_condition_formats_are_source_reconciled(value,unit,operator,matched):
 text='Processor: 5th Generation Intel Core i5 or above;'
 criterion={'field':'processor','operator':'baseline','expected':'5th Generation Intel Core i5','quote':text}
 condition={'value_text':value,'unit_text':unit,'operator':operator,'quote':text}
 assert represented_condition(criterion,condition) is matched
 condition['quote']='An unrelated processor clause'
 assert not represented_condition(criterion,condition)


@pytest.mark.parametrize('adjective', ['offered', 'proposed', 'supplied', 'required'])
def test_generic_product_adjective_is_not_a_model(adjective):
    text = f'The {adjective} laptop must have at least 32 GB RAM.'
    req, span = inputs(text, numeric(text, '32'))
    plan = build_check_plan(req, span)
    assert [c['field'] for c in plan['criteria']] == ['ram_gb']
    assert plan['criteria'][0]['expected'] == '32'
    assert plan['coverage'] == 'complete'
