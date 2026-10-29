"""Pure source-rule tests: no model calls, DB writes or local audit fixtures."""
from copy import deepcopy

from tenderready.clause_rules import procedural_candidates, reconcile_clause


def row(text, page=3, **fields):
    return {'id':'existing-id','page':page,'text':text,'excerpt':text,'category':'required_information',
        'obligation':'unclear','obligation_quote':None,'numeric_conditions':[], 'date_conditions':[],
        'review_reasons':['Model reasoning'], 'confidence':'high', **fields}


def grounded(proposal, page_text):
    assert proposal['text'] in page_text
    assert proposal['excerpt'] in page_text
    assert proposal['requires_human_review']
    for condition in proposal['numeric_conditions'] + proposal['date_conditions']:
        assert condition['quote'] in proposal['excerpt']
        if 'value_text' in condition:
            assert condition['value_text'] in condition['quote']
            assert condition['unit_text'] is None or condition['unit_text'] in condition['quote']
        else:
            assert condition['boundary_text'] in condition['quote']
    for ref in proposal['reconciliation']['evidence']:
        assert page_text[ref['start_offset']:ref['end_offset']] == ref['text']


def test_at_delivery_is_an_event_not_a_later_date_and_keeps_other_dates():
    text='8.1 Supplier is required to submit a guarantee of 7% at the time of delivery of goods; certificate expiry is before 30 June 2027.'
    original=row(text,obligation='mandatory',date_conditions=[
        {'relation':'on_or_after','boundary_text':'at the time of delivery of goods','quote':text},
        {'relation':'before','boundary_text':'30 June 2027','quote':text}])
    result=reconcile_clause(original,{3:text})
    assert result['date_conditions'][-1]['relation']=='relative'
    assert result['date_conditions'][0]['relation']=='before'
    assert result['temporal_conditions'][0]['relation']=='at_event'
    assert result['temporal_conditions'][0]['event_text']=='at the time of delivery of goods'
    grounded(result,text)
    assert original['date_conditions'][0]['relation']=='on_or_after'
    assert reconcile_clause(result,{3:text}) is None


def test_ambiguous_validity_never_becomes_minimum_or_calendar_expiry():
    text='8.3 Bank guarantee shall be valid up to six months at the time of delivery of goods.'
    result=reconcile_clause(row(text),{3:text})
    assert result['date_conditions'][0]['relation']=='unspecified'
    assert result['numeric_conditions']==[]
    assert 'clarification' in ' '.join(result['review_reasons'])
    grounded(result,text)


def test_turnover_preserves_currency_per_year_and_no_invented_calendar_anchor():
    text='3.3 The bidder shall have minimum turnover of Rs. Twelve lakhs per annum during each of the \nlast five years. Attested tax returns must be submitted.'
    result=reconcile_clause(row(text),{3:text})
    assert result['numeric_conditions'][0]['value_text']=='Twelve lakhs'
    assert result['numeric_conditions'][0]['unit_text']=='Rs.'
    assert result['numeric_conditions'][0]['operator']=='>='
    assert result['date_conditions'][0]['boundary_text']=='during each of the \nlast five years'
    assert result['temporal_conditions'][0]['anchor_date'] is None
    assert result['temporal_conditions'][0]['frequency_text']=='per annum'
    grounded(result,text)
    unrelated='The bidder shall report aggregate turnover over three years.'
    assert reconcile_clause(row(unrelated),{3:unrelated}) is None


def test_optional_scanning_is_advice_not_usable_numeric_threshold():
    text='3) Documents generally can be in PDF / XLS formats. Documents may be scanned with 150 dpi for a smaller file.'
    original=row(text,numeric_conditions=[{'operator':'=','value_text':'150','unit_text':'dpi','quote':text}],
                 review_reasons=['Files must be PDF; 150 dpi is mandatory.'])
    result=reconcile_clause(original,{3:text})
    assert result['numeric_conditions']==[]
    assert result['advisory_conditions'][0]['value_text']=='150'
    assert result['obligation']=='unclear' and result['disposition']=='advisory'
    assert result['previous_model_review_reasons']==original['review_reasons']
    assert all('150 dpi is mandatory' not in reason for reason in result['review_reasons'])
    grounded(result,text)
    required='Documents must be scanned with 150 dpi.'
    assert reconcile_clause(row(required,numeric_conditions=original['numeric_conditions']),{3:required}) is None


def test_usb_version_labels_are_not_measurement_units():
    text='Port:- USB (4*3.1 & 2*2.0)'
    result=reconcile_clause(row(text,numeric_conditions=[
        {'operator':'=','value_text':'4','unit_text':'3.1','quote':text},
        {'operator':'=','value_text':'2','unit_text':'2.0','quote':text}]),{3:text})
    assert result['numeric_conditions']==[]
    assert result['unresolved_interpretations'][0]['kind']=='usb_port_version_count'
    grounded(result,text)


def test_portal_description_is_reference_but_bidder_encryption_is_not():
    text='7) All documents would be encrypted using PKI. The uploaded documents become readable by bid openers after opening on the portal.'
    result=reconcile_clause(row(text,date_conditions=[{'relation':'after','boundary_text':'opening','quote':text}]),{3:text})
    assert result['disposition']=='reference'
    assert result['date_conditions']==[]
    assert result['obligation']=='unclear'
    grounded(result,text)
    required='Bidders must encrypt their files. All documents would be encrypted by the server.'
    assert reconcile_clause(row(required),{3:required}) is None
    mixed='The supplier should encrypt its bid. All documents would be encrypted by the server.'
    assert reconcile_clause(row(mixed),{3:mixed}) is None


def test_contacts_and_helpdesk_are_reference_without_swallowing_bidder_task():
    contacts='Officer\nTel: 123\nFax: 456\nE-mail: help@example.org'
    assert reconcile_clause(row(contacts),{3:contacts})['disposition']=='reference'
    helpdesk='Queries may be directed to the 24x7 Helpdesk. Contact us at 123.'
    assert reconcile_clause(row(helpdesk),{3:helpdesk})['numeric_conditions']==[]
    required='The bidder should make a note of its Tender ID to obtain help from the Helpdesk.'
    assert reconcile_clause(row(required),{3:required}) is None


def test_advised_never_becomes_mandatory_from_model_rationale():
    text='Bidders are advised to register their email address.'
    result=reconcile_clause(row(text,obligation='mandatory',obligation_quote=text,
        review_reasons=['Advised is treated as mandatory.']),{3:text})
    assert result['obligation']=='unclear' and result['obligation_quote'] is None
    assert result['previous_model_review_reasons']==['Advised is treated as mandatory.']
    assert result['disposition']=='advisory'
    assert 'No mandatory obligation' in ' '.join(result['review_reasons'])


def test_split_boq_halves_map_to_same_complete_numbered_clause():
    first='5) Bidders are required to download the BoQ file and fill white cells with details (such as'
    last='name of the bidder). No other cells should change. Save without changing the filename.'
    complete=first+'\n'+last
    page='SUBMISSION OF BIDS\n'+complete+'\n6) Follow the server time.\n'
    left=reconcile_clause(row(first),{3:page});right=reconcile_clause(row(last),{3:page})
    assert left['text']==right['text']==complete
    grounded(left,page);grounded(right,page)
    assert 'Follow the server time' not in left['text']
    # Never steal continuation from another page or another numbered clause.
    assert reconcile_clause(row(first),{3:first,4:last}) is None


def test_emd_and_fod_same_page_address_restored_without_next_clause():
    emd='4.9 Original hard copy of EMD shall be sent in a sealed envelope to the officer, Building'
    emd_end='C, 45 Main Road. Failing which bids will not be considered.'
    fod='14.2 Supply shall be made on FOD Basis to the following address:-'
    address='Officer\nRoom 12, North Wing\n45 Main Road\nTel: 123\nFax: 456\nE-mail: help@example.org'
    page=emd+'\n'+emd_end+'\n5. Financial bid must be online.\n'+fod+'\n\n'+address+'\n14.3 Delivery within seven days.'
    result=reconcile_clause(row(emd),{3:page})
    assert result['text']==emd+'\n'+emd_end
    result=reconcile_clause(row(fod),{3:page})
    assert result['text']==fod+'\n\n'+address
    assert result['disposition']=='requirement'
    grounded(result,page)


def test_cover_boundary_does_not_merge_oem_with_boq_cover():
    text='6. OEM certificate shall be included.\n.pdf'
    page=text+'\nCover 2 - (Financial Bid)\n(to be submitted in BOQ format online)\nSl. No. Document File Type\n1. Financial bid as per Annexure IV .xlsx\n'
    assert reconcile_clause(row(text),{3:page}) is None
    candidates=procedural_candidates({3:page})
    assert len(candidates)==1
    assert candidates[0]['text']=='1. Financial bid as per Annexure IV .xlsx'
    grounded(candidates[0],page)
    assert candidates[0]['confidence'] in {'high', 'medium', 'low'}
    assert procedural_candidates({3:'1. Financial bid as per Annexure IV .xlsx'})==[]


def test_ambiguous_location_and_missing_source_are_not_guessed():
    text='Bidders are advised to register.'
    assert reconcile_clause(row(text),{3:text+'\n'+text}) is None
    assert reconcile_clause(row(text),{4:text}) is None
    original=row(text); before=deepcopy(original)
    reconcile_clause(original,{3:text})
    assert original==before
