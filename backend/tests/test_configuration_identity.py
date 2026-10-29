from types import SimpleNamespace
from tenderready.amendments import equivalent
from tenderready.verification import threshold_sentence


def requirement(scope):
    text='The product must have at least 32 GB RAM.'
    return SimpleNamespace(statement=text,category='numeric_threshold',obligation='mandatory',
        condition={'confidence':'high','numeric_conditions':[{'operator':'>=','value_text':'32','unit_text':'GB','quote':text}],
            'source_context':[{'kind':'product_scope','text':scope}], 'date_conditions':[], 'review_reasons':[]})


def test_configuration_change_is_not_unchanged_even_with_identical_threshold_text():
    assert equivalent(requirement('Configuration A'),requirement('Configuration A'))
    assert not equivalent(requirement('Configuration A'),requirement('Configuration B'))


def test_scoped_threshold_never_gets_global_automatic_amendment_identity():
    assert threshold_sentence(requirement('Configuration A')) is None
