"""Zero-provider source reconciliation; quantities are never minimum thresholds."""
from copy import deepcopy
import pytest

from tenderready.quantity_rules import quantity_candidates


ANTICIPATED = '''2
Item Minimum required specification Anticipated
Requirement
Laptop/Notebook
Configuration A
Memory: 8 GB or below;
7
Laptop/Notebook
Configuration B
Memory: 4 GB or above;
9
Tablet Screen Size: 8.9 inch or above;
Memory: 2GB or higher;
3
2. Eligibility Criteria for Bidders:-
3.1 The bidder shall have minimum 2 years of experience.
'''
SCHEDULE = '''9
PRICE SCHEDULE
Item Description Quantity Unit Cost
(without tax)
1 2 3 4 5 6 7 8
1.00 Laptop/Notebook
of Configuration A
7.0000
2.00 Laptop/Notebook
of Configuration B
9.0000 0.0000 0.0000 INR Zero
Only
3.00 Tablets 3.0000 0.0000 0.0000 INR Zero
Only
Total in
Figures
0.0000 0.0000 INR Zero Only
'''


def assert_sources(rows,pages):
    source={p['page']:p['text'] for p in pages}
    for row in rows:
        text=source[row['page']]
        assert text[row['start_offset']:row['end_offset']] == row['text'] == row['excerpt']
        for context in row['source_context']:
            assert source[context['page']][context['start_offset']:context['end_offset']] == context['text']
        for condition in row['quantity_conditions']:
            assert condition['quote'] in text
            assert text[condition['value_start_offset']:condition['value_end_offset']] == condition['value_text']
        for ref in row['quantity_references']:
            assert source[ref['page']][ref['start_offset']:ref['end_offset']] == ref['text']
        assert row['requires_human_review'] is True
        assert row['review_status'] == 'awaiting_review'
        assert row['obligation'] == 'unclear'
        assert row['provenance'] == 'deterministic_source_reconciliation'
        assert all(c['operator']=='unspecified' for c in row['numeric_conditions'])


def test_explicit_anticipated_quantities_keep_each_configuration_and_not_minimum():
    pages=[{'page':2,'text':ANTICIPATED}]
    rows=quantity_candidates(pages)
    assert len(rows)==3
    assert [(r['quantity_conditions'][0]['scope'],r['quantity_conditions'][0]['count']) for r in rows] == [
        ('Configuration A',7),('Configuration B',9),('Tablet',3)]
    assert {r['quantity_conditions'][0]['kind'] for r in rows} == {'anticipated'}
    assert all(r['quantity_conditions'][0]['unit_text'] is None for r in rows)
    assert_sources(rows,pages)


def test_boq_first_quantity_column_is_separate_from_zero_price_placeholders():
    pages=[{'page':9,'text':SCHEDULE}]
    rows=quantity_candidates(pages)
    assert len(rows)==3
    assert [r['quantity_conditions'][0]['count'] for r in rows] == [7,9,3]
    assert [r['quantity_conditions'][0]['value_text'] for r in rows] == ['7.0000','9.0000','3.0000']
    assert all(len(r['numeric_conditions'])==1 for r in rows)
    assert {r['quantity_conditions'][0]['kind'] for r in rows} == {'schedule'}
    assert_sources(rows,pages)


def test_corresponding_schedule_and_anticipated_rows_have_exact_cross_references():
    pages=[{'page':2,'text':ANTICIPATED},{'page':9,'text':SCHEDULE}]
    original=deepcopy(pages)
    rows=quantity_candidates(pages)
    assert pages==original
    assert len(rows)==6
    assert all(len(r['quantity_references'])==1 and not r['quantity_conflict'] for r in rows)
    assert all(r['quantity_references'][0]['page'] != r['page'] for r in rows)
    assert_sources(rows,pages)


def test_disagreeing_quantities_are_flagged_without_overwriting_either_source():
    pages=[{'page':2,'text':ANTICIPATED},{'page':9,'text':SCHEDULE.replace('7.0000','8.0000')}]
    rows=quantity_candidates(pages)
    conflicting=[r for r in rows if r['quantity_conflict']]
    assert len(conflicting)==2
    assert {r['quantity_conditions'][0]['count'] for r in conflicting}=={7,8}
    assert all(r['confidence']=='low' and any('disagree' in x for x in r['review_reasons']) for r in conflicting)
    assert_sources(rows,pages)


def test_unlabeled_numbers_do_not_create_quantities():
    text='Configuration A\nMemory: 8 GB\n10\nConfiguration B\nMemory: 4GB\n10\n'
    assert quantity_candidates([{'page':1,'text':text}]) == []
    assert quantity_candidates([{'page':1,'text':SCHEDULE.replace('Item Description Quantity Unit Cost','Random heading')}]) == []


def test_multiple_anticipated_numeric_cells_require_review_instead_of_guessing():
    rows=quantity_candidates([{'page':2,'text':ANTICIPATED.replace('8 GB or below;\n7','8 GB or below;\n4\n7')}])
    ambiguous=next(r for r in rows if r['source_context'][-1]['text']=='Configuration A')
    assert ambiguous['quantity_conditions']==ambiguous['numeric_conditions']==[]
    assert ambiguous['confidence']=='low'
    assert any('ambiguous' in reason for reason in ambiguous['review_reasons'])


def test_zero_quantity_and_description_year_are_not_reinterpreted_as_quantity():
    pages=[{'page':9,'text':SCHEDULE.replace('7.0000','0.0000').replace('Configuration B\n9.0000','Configuration B 2020 edition\n9.0000')}]
    rows=quantity_candidates(pages)
    assert len(rows)==3
    assert rows[0]['quantity_conditions']==[]
    assert rows[1]['quantity_conditions']==[]
    assert rows[2]['quantity_conditions'][0]['count']==3


def test_units_are_only_used_when_written_and_invalid_pages_rejected():
    text='Item Description Quantity Unit Cost\n1.00 Tablets 4 Nos. 0.0000\nTotal in Figures\n'
    rows=quantity_candidates([{'page':4,'text':text}])
    assert len(rows)==1 and rows[0]['quantity_conditions'][0]['unit_text']=='Nos.'
    assert_sources(rows,[{'page':4,'text':text}])
    for bad in (0,-1,True,'2'):
        with pytest.raises(ValueError):
            quantity_candidates([{'page':bad,'text':text}])
