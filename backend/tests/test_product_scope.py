from copy import deepcopy
from types import SimpleNamespace

import pytest

from tenderready.product_scope import requirement_scope, scope_evidence
from tenderready.verification import read_facts


def span(text, *, sid='span', did='tender', page=2, start=0, wid='workspace'):
    return SimpleNamespace(id=sid, document_version_id=did, page=page, start_offset=start,
        end_offset=start + len(text), text=text, workspace_id=wid)


def requirement(label='Configuration A', *, source=None):
    source = source or span('Heading\n' + label + '\nRAM: at least 32 GB')
    start = source.text.index(label) + source.start_offset
    context = {'kind': 'product_scope', 'text': label, 'page': source.page,
        'source_document_id': source.document_version_id, 'start_offset': start, 'end_offset': start + len(label)}
    return SimpleNamespace(workspace_id='workspace', source_span_id=source.id, statement='RAM: at least 32 GB',
        condition={'source_context': [context]}), source


def evidence(text, *, did='evidence', kind='datasheet', page=1, wid='workspace'):
    doc = SimpleNamespace(id=did, filename=did + '.pdf', workspace_id=wid)
    entry = SimpleNamespace(evidence_type=kind)
    source = span(text, sid=did + '-span', did=did, page=page, wid=wid)
    return (doc, entry, read_facts(source)), source


def run(req, source, *documents):
    return scope_evidence(req, {row[0].id: row for row, _ in documents},
        {row[0].id: [page] for row, page in documents}, [source])


def test_no_scope_leaves_existing_model_verification_and_facts_unchanged():
    req = SimpleNamespace(workspace_id='workspace', condition={})
    item, source = evidence('Model: Atlas A14\nRAM: 32 GB')
    result = scope_evidence(req, {'evidence': item}, {'evidence': [source]})
    assert result['summary']['state'] == 'unscoped' and result['by_doc']['evidence'] is item
    assert result['checks'] == [] and result['requires_review'] is False


def test_grounded_a_header_uses_only_matching_document_and_exact_source_refs():
    req, source = requirement()
    a = evidence('Configuration: A\nModel: Atlas A14\nRAM: 32 GB', did='a')
    b = evidence('Configuration B\nModel: Atlas B14\nRAM: 64 GB', did='b')
    before = deepcopy(a[0][2])
    result = run(req, source, a, b)
    assert result['summary']['state'] == 'matched' and result['matched']
    assert set(result['by_doc']) == {'a'}
    assert result['summary']['documents'] == [{'id': 'a', 'filename': 'a.pdf'}]
    ram = next(f for f in result['by_doc']['a'][2] if f['field'] == 'ram_gb')
    assert ram['raw_value'] == '32 GB' and ram['normalized']['product_scope'] == 'configuration:a'
    ref = ram['normalized']['scope_sources'][0]
    assert ref['quote'] == 'Configuration: A' and ref['page'] == 1 and ref['document_version_id'] == 'a'
    assert a[0][2] == before
    assert any(c['outcome'] == 'not_applicable' and c['document_id'] == 'b' for c in result['checks'])


@pytest.mark.parametrize('mutation', [
    {'page': 3}, {'source_document_id': 'other'}, {'start_offset': 0}, {'end_offset': 1000},
    {'text': 'Configuration B'},
])
def test_requirement_heading_must_match_its_actual_tender_page_and_offsets(mutation):
    req, source = requirement()
    req.condition['source_context'][0].update(mutation)
    assert requirement_scope(req, [source])['state'] == 'needs_review'
    result = run(req, source, evidence('Configuration A\nRAM: 32 GB'))
    assert result['summary']['state'] == 'needs_review' and result['by_doc'] == {}


def test_missing_original_spans_does_not_trust_context_metadata():
    req, _ = requirement()
    assert requirement_scope(req)['state'] == 'needs_review'


def test_context_without_offsets_requires_unique_exact_source_text():
    req, source = requirement()
    context = req.condition['source_context'][0]
    del context['start_offset']; del context['end_offset']
    assert requirement_scope(req, [source])['state'] == 'scoped'
    source.text += '\nConfiguration A'
    source.end_offset = len(source.text)
    assert requirement_scope(req, [source])['state'] == 'needs_review'


def test_distinct_a_b_sections_do_not_mix_model_or_ram_facts():
    req, source = requirement()
    item = evidence('Configuration A\nModel: Atlas A14\nRAM: 32 GB\nConfiguration B\nModel: Atlas B14\nRAM: 16 GB')
    result = run(req, source, item)
    assert result['matched'] and [f['raw_value'] for f in result['by_doc']['evidence'][2]] == ['Atlas A14', '32 GB']


def test_duplicate_fact_quotes_across_sections_abstain_instead_of_guessing_offsets():
    req, source = requirement()
    result = run(req, source, evidence('Configuration A\nModel: Atlas A14\nRAM: 16 GB\nConfiguration B\nModel: Atlas B14\nRAM: 16 GB'))
    assert result['summary']['state'] == 'needs_review'
    assert all(f['field'] != 'ram_gb' for f in result['by_doc']['evidence'][2])
    assert any('repeated' in c['rationale'] for c in result['checks'])


def test_no_header_inheritance_across_pages():
    req, source = requirement()
    item, first = evidence('Configuration A\nModel: Atlas A14')
    second = span('RAM: 32 GB', sid='page2', did='evidence', page=2)
    item[2].extend(read_facts(second))
    result = scope_evidence(req, {'evidence': item}, {'evidence': [first, second]}, [source])
    assert result['summary']['state'] == 'needs_review'
    assert all(f['field'] != 'ram_gb' for f in result['by_doc']['evidence'][2])


def test_headers_can_scope_later_spans_on_same_page_with_absolute_offsets():
    req, source = requirement()
    item, first = evidence('Configuration A\nModel: Atlas A14')
    second = span('RAM: 32 GB', sid='second-span', did='evidence', page=1, start=first.end_offset + 1)
    item[2].extend(read_facts(second))
    result = scope_evidence(req, {'evidence': item}, {'evidence': [first, second]}, [source])
    assert result['matched'] and any(f['field'] == 'ram_gb' for f in result['by_doc']['evidence'][2])


@pytest.mark.parametrize('heading', ['Configuration A or B', 'Configuration: C', 'Datasheet for Configuration A'])
def test_ambiguous_unknown_or_prose_headings_never_assign_numeric_facts(heading):
    req, source = requirement()
    result = run(req, source, evidence(heading + '\nModel: Atlas A14\nRAM: 32 GB'))
    assert result['summary']['state'] == 'needs_review' and result['by_doc'] == {}


def test_unknown_heading_stops_prior_configuration_scope():
    req, source = requirement()
    result = run(req, source, evidence('Configuration A\nModel: Atlas A14\nConfiguration C\nRAM: 32 GB'))
    assert result['summary']['state'] == 'needs_review'
    assert all(f['field'] != 'ram_gb' for f in result['by_doc']['evidence'][2])


def test_tablet_and_tablets_are_same_explicit_scope_without_equating_laptops():
    req, source = requirement('Tablets')
    result = run(req, source, evidence('Product type: Tablet\nModel: Tab T8\nRAM: 4 GB'))
    assert result['matched'] and result['required_scope']['key'] == 'product:tablet'


def test_multiple_models_in_same_option_need_review():
    req, source = requirement()
    result = run(req, source, evidence('Configuration A\nModel: Atlas A14\nModel: Atlas A16\nRAM: 32 GB'))
    assert result['summary']['state'] == 'needs_review' and result['by_doc'] == {}


def test_different_models_across_matching_documents_never_claim_one_match():
    req, source = requirement()
    result = run(req, source, evidence('Configuration A\nModel: Atlas A14\nRAM: 32 GB', did='a'),
        evidence('Configuration A\nModel: Atlas A16\nRAM: 32 GB', did='other'))
    assert not result['matched'] and result['summary']['state'] == 'needs_review'
    assert any('different models' in c['rationale'] for c in result['checks'])


def test_wrong_configuration_is_missing_not_a_numeric_match():
    req, source = requirement()
    result = run(req, source, evidence('Configuration B\nModel: Atlas B14\nRAM: 32 GB'))
    assert result['summary']['state'] == 'missing' and result['by_doc'] == {}
    assert any(c['outcome'] == 'missing' for c in result['checks'])


def test_company_documents_are_left_to_existing_entity_and_date_checks():
    req, source = requirement()
    cert = evidence('Bidder: Example Supplier\nCertificate number: 12', kind='certificate')
    result = run(req, source, cert)
    assert result['by_doc']['evidence'] is cert[0] and result['summary']['state'] == 'missing'


def test_other_workspace_documents_cannot_be_assigned():
    req, source = requirement()
    with pytest.raises(ValueError, match='requirement workspace'):
        run(req, source, evidence('Configuration A\nRAM: 32 GB', wid='other'))


def test_multiple_required_options_remain_review_even_with_matching_documents():
    req, source = requirement()
    second = span('Configuration B', sid='tender-b', did='tender', page=3)
    req.condition['source_context'].append({'kind':'product_scope','text':'Configuration B','page':3,
        'source_document_id':'tender','start_offset':0,'end_offset':len(second.text)})
    assert requirement_scope(req, [source, second])['state'] == 'needs_review'


@pytest.mark.parametrize('label,statement', [
    ('Configuration A', 'RAM: at least 32 GB'),
    ('Configuration B', 'RAM: at least 16 GB'),
])
def test_valid_heading_cannot_be_swapped_onto_other_configuration_requirement(label, statement):
    source = span('Configuration A\nRAM: at least 16 GB\nConfiguration B\nRAM: at least 32 GB')
    req, _ = requirement(label, source=source)
    req.statement = statement
    result = requirement_scope(req, [source])
    assert result['state'] == 'needs_review' and 'not uniquely under' in result['reason']
    mapped = run(req, source, evidence(label + '\nModel: Atlas A14\nRAM: 64 GB'))
    assert not mapped['matched'] and mapped['by_doc'] == {}


@pytest.mark.parametrize('boundary', ['Configuration C', 'Configuration A or B', 'Product type: Unknown'])
def test_unknown_heading_between_cited_scope_and_requirement_blocks_inheritance(boundary):
    req, source = requirement(source=span('Configuration A\nRAM: 8 GB\n' + boundary + '\nRAM: at least 32 GB'))
    assert requirement_scope(req, [source])['state'] == 'needs_review'


def test_duplicate_requirement_under_different_headings_cannot_be_resolved_by_selected_context():
    req, source = requirement(source=span('Configuration A\nRAM: at least 32 GB\nConfiguration B\nRAM: at least 32 GB'))
    assert requirement_scope(req, [source])['state'] == 'needs_review'


def test_requirement_does_not_inherit_heading_from_another_page():
    req, first = requirement(source=span('Configuration A'))
    second = span(req.statement, sid='actual-source', page=3)
    req.source_span_id = second.id
    assert requirement_scope(req, [first, second])['state'] == 'needs_review'


def test_heading_after_requirement_does_not_scope_it_backwards():
    req, source = requirement(source=span('RAM: at least 32 GB\nConfiguration A'))
    assert requirement_scope(req, [source])['state'] == 'needs_review'


@pytest.mark.parametrize('with_offsets', [False, True])
def test_overlapping_spans_represent_one_source_position_and_heading(with_offsets):
    whole = span('Heading\nConfiguration A\nRAM: at least 32 GB\nFooter')
    req, _ = requirement(source=whole)
    if not with_offsets:
        for key in ('start_offset', 'end_offset'):
            req.condition['source_context'][0].pop(key)
    start = whole.text.index(req.statement)
    child = span(req.statement, sid='exact-clause', start=start)
    overlapping = span(whole.text[8:], sid='overlapping-page', start=8)
    req.source_span_id = child.id
    result = requirement_scope(req, [whole, child, overlapping])
    assert result['state'] == 'scoped' and result['key'] == 'configuration:a'


def test_gap_between_header_and_requirement_does_not_hide_an_unseen_heading():
    req, header = requirement(source=span('Configuration A'))
    source = span(req.statement, sid='actual-clause', start=100)
    req.source_span_id = source.id
    assert requirement_scope(req, [header, source])['state'] == 'needs_review'


def test_conflicting_overlapping_spans_require_review():
    req, source = requirement()
    changed = span(source.text.replace('Configuration A', 'Configuration B'), sid='conflicting-copy')
    assert requirement_scope(req, [source, changed])['state'] == 'needs_review'


@pytest.mark.parametrize('label,statement', [
    ('Configuration A', 'Memory: 8 GB or below;'),
    ('Configuration A', 'Hard Disk: 500 GB or above;'),
    ('Configuration B', 'Memory: 4 GB or above'),
    ('Configuration B', 'Storage: 128 GB Flash or above'),
    ('Tablet', 'Storage: 16 GB or Higher;'),
    ('Tablet', 'Memory: 2GB or higher;'),
    ('Tablet', 'Tablet Screen Size: 8.9 inch or above;'),
])
def test_mea_style_table_keeps_a_b_and_inline_tablet_clauses_source_grounded(label, statement):
    source = span('Item Minimum required specification\nConfiguration A\nMemory: 8 GB or below;\n'
        'Hard Disk: 500 GB or above;\nConfiguration B\nMemory: 4 GB or above\n'
        'Storage: 128 GB Flash or above\nTablet Screen Size: 8.9 inch or above;\n'
        'Storage: 16 GB or Higher;\nMemory: 2GB or higher;')
    req, _ = requirement(label, source=source)
    req.statement = statement
    assert requirement_scope(req, [source])['state'] == 'scoped'


def test_tablet_inline_heading_stops_previous_configuration_scope():
    req, source = requirement(source=span('Configuration A\nRAM: 8 GB\n'
        'Tablet Screen Size: 8.9 inch or above;\nRAM: at least 32 GB'))
    assert requirement_scope(req, [source])['state'] == 'needs_review'


def test_combined_row_can_include_its_own_heading_but_not_another_option():
    prefix = 'Laptop/Ultrabook/No\ntebook/Macbook or\ndevices of similar\ncategories of\n'
    statement = prefix + 'Configuration B\nRAM: at least 32 GB'
    source = span('Configuration A\nRAM: 16 GB\n' + statement)
    req, _ = requirement('Configuration B', source=source)
    req.statement = statement
    assert requirement_scope(req, [source])['state'] == 'scoped'
    req.statement = source.text
    assert requirement_scope(req, [source])['state'] == 'needs_review'


def test_whole_webcam_clause_is_not_duplicate_of_longer_speaker_clause():
 req,source=requirement('Configuration B',source=span(
  'Configuration A\nIntegrated HD Webcam & Speaker\nConfiguration B\nIntegrated HD Webcam'))
 req.statement='Integrated HD Webcam'
 assert requirement_scope(req,[source])['state']=='scoped'
 assert requirement_scope(req,[source])['key']=='configuration:b'
 # A genuine duplicate remains unresolved, even if only one has a semicolon.
 source.text=source.text.replace(' & Speaker',';')
 source.end_offset=len(source.text)
 start=source.text.index('Configuration B')
 req.condition['source_context'][0].update(start_offset=start,end_offset=start+15)
 assert requirement_scope(req,[source])['state']=='needs_review'
