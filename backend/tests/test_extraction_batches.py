"""The batch planner needs no provider or PDF fixture to preserve provenance."""
import pytest

from tenderready.extraction_batches import plan_batches


TABLE = '''2
Item Minimum required specification Anticipated
Requirement
Laptop/Ultrabook/No
tebook/Macbook or
devices of similar
categories of
Configuration A
Memory: 8 GB or below;
Hard Disk: 500 GB or above;
10
Laptop/Ultrabook/No
tebook/Macbook or
devices of similar
categories of
Configuration B
Memory: 4 GB or above
Storage: 128 GB Flash or above
10
Tablet Screen Size: 8.9 inch or above;
Memory: 2GB or higher;
2

2. The two bid system shall be followed.

3. Eligibility Criteria for Bidders:-
3.1 The bidder shall have minimum 2 years of experience.
'''


def assert_exact_coverage(text, batches, maximum):
    assert batches[0].start == 0 and batches[-1].end == len(text)
    assert ''.join(text[b.start:b.end] for b in batches) == text
    assert all(a.end == b.start for a, b in zip(batches, batches[1:]))
    assert all(0 < b.end - b.start <= maximum for b in batches)
    for batch in batches:
        for context in batch.contexts:
            assert context.text == text[context.start:context.end]
            assert context.text


def test_configuration_groups_keep_exact_scope_and_wrapped_names():
    batches = plan_batches(TABLE)
    assert_exact_coverage(TABLE, batches, 1500)
    scopes = [[c.text for c in b.contexts if c.kind == 'product_scope'] for b in batches]
    assert scopes == [[], ['Configuration A'], ['Configuration B'], ['Tablet'], []]
    for batch in batches:
        fragment = TABLE[batch.start:batch.end]
        scope = [c.text for c in batch.contexts if c.kind == 'product_scope']
        if 'Memory: 8' in fragment:
            assert scope == ['Configuration A']
            assert fragment.startswith('Laptop/Ultrabook/No')
            assert 'Memory: 4' not in fragment
        if 'Memory: 4' in fragment:
            assert scope == ['Configuration B']
        if 'Memory: 2' in fragment:
            assert scope == ['Tablet']
        if 'Eligibility' in fragment:
            assert batch.contexts == ()
    headers = [c for b in batches for c in b.contexts if c.kind == 'table_header']
    assert len(headers) == 3
    assert all(c.text == 'Item Minimum required specification Anticipated\nRequirement' for c in headers)


def test_split_large_configuration_carries_context_without_crossing_scope():
    text = 'Configuration A\n' + ('Memory: 8 GB or below;\n' * 60) + 'Configuration B\nMemory: 32 GB or above;\n4. Eligibility\nThe bidder must register.\n'
    batches = plan_batches(text, max_chars=300)
    assert_exact_coverage(text, batches, 300)
    for batch in batches:
        chunk = text[batch.start:batch.end]
        scope = [c.text for c in batch.contexts if c.kind == 'product_scope']
        if '8 GB' in chunk:
            assert scope == ['Configuration A']
        elif '32 GB' in chunk:
            assert scope == ['Configuration B']
        elif 'Eligibility' in chunk:
            assert not scope


def test_short_non_table_page_is_unchanged():
    text = '1. The bidder must submit a certificate.\n2. Delivery within ten days.\n'
    batches = plan_batches(text)
    assert len(batches) == 1
    assert batches[0].contexts == ()
    assert_exact_coverage(text, batches, 1500)


def test_prefer_clause_boundaries_without_rewriting_whitespace():
    text = '1. Intro\n' + '3.1 The bidder shall submit a certificate.\n' * 40 + '\n3.2 Other documents.\n'
    batches = plan_batches(text, max_chars=150)
    assert_exact_coverage(text, batches, 150)
    assert all(text[b.start:b.end].rstrip().endswith(('.', 'Intro')) for b in batches)


def test_long_unbroken_line_bounded_and_all_characters_retained():
    text = 'x' * 4000
    batches = plan_batches(text, max_chars=1000)
    assert_exact_coverage(text, batches, 1000)
    assert len(batches) == 4


def test_unknown_headings_do_not_invent_product_context():
    text = 'This sentence mentions Configuration A but is not a heading.\nMemory: 8 GB\n'
    assert not plan_batches(text)[0].contexts
    assert plan_batches('') == []
    with pytest.raises(ValueError):
        plan_batches('x', max_chars=0)
