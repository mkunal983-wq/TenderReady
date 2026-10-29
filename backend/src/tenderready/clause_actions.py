"""Bounded routing of source-grounded procurement actions, never compliance proof.

A task asks a supplier to do something or record contract acceptance. It does not
validate certificates, signatures, portal state, legal eligibility or completion.
"""
import re

# Ordered by the most specific action. Matching uses original tender text only.
_RULES = (
    ('submission_receipt', r'\b(?:received without EMD|received other than online|not submitting any|required documents online|Online bids.*demand draft)\b',
     r'\b(?:bid|bids|bidders|tender|EMD)\b',
     'Check the submission and EMD receipts',
     'Check the quoted submission channel and required EMD record. Retain the portal and physical receipts where required. Resolve any conflicting amount before payment; a local upload is not proof of submission.'),
    ('opening_schedule', r'\b(?:date of opening.*holiday|Critical Dates)\b', r'\b(?:tender|page|working day)\b',
     'Confirm the current tender schedule',
     'Consult the cited schedule and official notices. Record the actual opening date and any announced holiday change. No working-day calendar or revised date is assumed.'),
    ('fixed_rates', r'\bno request for increase in quoted\b', r'\brates\b',
     'Confirm the quoted rates can be maintained',
     'Record the applicable validity period and confirm that the pricing plan follows the quoted restriction. This is an acceptance task, not an inferred pricing guarantee.'),

    ('portal_registration', r'\b(?:enroll|enrolment|enrollment|register|registration process|unique username|logs in)\b',
     r'\b(?:bidder|bidders|CPP|Procurement|DSC)\b',
     'Complete portal registration',
     'Complete the stated portal/account step. Keep a registration confirmation or timestamp; never upload passwords, signing keys or tokens.'),
    ('digital_signature', r'\b(?:digital signature certificate|digital s ignature certificate|valid DSC)\b',
     r'\b(?:bidder|bidders|tenderer|participation)\b',
     'Check the digital signing setup',
     'Check the stated certificate class, validity and portal registration. Retain confirmation without exposing the private key. This app cannot verify the portal or certifying authority.'),
    ('boq', r'\b(?:BOQ|financial bid as per Annexure)\b', r'\b(?:download|unprotected cells|\.xls|Annexure)\b',
     'Prepare the financial bid',
     'Use the original financial-bid template. Fill only the permitted fields, check bidder details and prices, and retain the completed file. Do not change protected cells.'),
    ('submission_format', r'\btwo (?:bid|envelope) system\b', r'\b(?:Technical|Financial)\b',
     'Prepare separate technical and financial bids',
     'Prepare the envelopes/files exactly as stated. Retain a submission checklist and portal receipt; document presence alone does not establish submission.'),
    ('portal_instructions', r'\b(?:instructions provided|Instruction to Tenderer|corrigendum|unique Tender ID|server time|payment option|bid summary|queries relating)\b',
     r'\b(?:bidder|bidders|tender|bid|CPP|Procurement)\b',
     'Follow the tender portal instruction',
     'Carry out the quoted portal instruction and record what was done. Use the portal clock for deadlines and keep the relevant receipt or acknowledgement. Do not assume a deadline from the current date.'),
    ('company_documents', r'\b(?:Income Tax return|registration and incorporation|undertaking that the bidder|proof of minimum|minimum \d+ years of experience)\b',
     r'\b(?:bidder|firm|company|experience|TIN|Tax)\b',
     'Collect the required company records',
     'Collect every document and period named in the clause. Check the legal entity, dates, relevant project scope and any signature/stamp requirements. Attach records for review; this task is not certificate or experience verification.'),
    ('authorization', r'\b(?:OEM Authorisation Certificate|original manufacturer)\b', r'\b(?:bidder|OEM)\b',
     'Determine whether OEM authorization is required',
     'Record whether the bidder is the OEM. If authorization is required, obtain it for the exact bidder and offered product, with the additional records named in the clause. Do not assume which branch applies.'),
    ('packing', r'\boriginal packing\b', r'\bmanufactur',
     'Check packing and labels before supply',
     'Check the original manufacturer packaging and every label named in the clause. Retain photos or inspection records for the supplied items.'),
    ('supply', r'\b(?:shall be supplied|supply shall be completed|immediately replaced)\b', r'\b(?:item|items|supply)\b',
     'Plan the supply or replacement action',
     'Record the actual purchase-order or defect event and follow the quoted delivery/replacement condition. Keep delivery or replacement receipts. No event date, penalty or deadline is assumed.'),
    ('bank_guarantee', r'\bbank guarantee shall be made in favour\b', r'\b(?:Accounts Officer|beneficiary)\b',
     'Check the bank-guarantee beneficiary',
     'Obtain the bank guarantee with the exact beneficiary stated in the clause. Check the issued document and retain it; authenticity requires the issuing bank.'),
    ('bid_validity', r'\b(?:validity of bid|bids shall be valid)\b', r'\b(?:months|days|opening)\b',
     'Confirm the bid-validity period',
     'Record the actual bid-opening date and confirm that the offered validity covers the stated period. Resolve any date change before calculating the end date.'),
    ('contract_terms', r'\b(?:Ministry reserves the right|Ministry at its discretion|Ministry may declare|Ministry shall reject|Ministry may consider|contract shall be awarded|committee will evaluate|Ministry shall shortlist|non transferability|unrealistic prices|no request for increase|payment will be made|payment against|no advance payment|EMD.*(?:forfeited|returned)|settlement of disputes|highest standards of ethics|in no way be binding|blacklisted and its EMD|fails to furnish)\b',
     r'\b(?:Ministry|bidder|bidders|tender|tenderer|contract|payment|EMD|agreement)\b',
     'Record acceptance of the contract condition',
     'Read the complete quoted condition and record how it affects your bid or contract plan. Buyer decisions, future events and legal acceptance cannot be established from a product datasheet. Closing this task does not verify that they occurred.'),
)


def action_for(text):
    """Return an action recipe, not a validation outcome or inferred deadline."""
    direct = literal_action(text)
    if direct:
        return direct
    flat = ' '.join(text.split())
    boq = re.fullmatch(r'\d+\.\d+\s+(Tablets|Laptop/Ultrabook/\s*Notebook/Macbook\s+or devices of\s+similar categories\s+of Configuration [AB])\s+(\d+\.\d+)(?:\s+0\.0+\s+0\.0+\s+INR Zero\s+Only)?', flat, re.I)
    if boq:
        return {'rule': 'boq_quantity', 'title': 'Use the stated BOQ quantity',
                'instruction': f'Prepare the financial-bid row for {boq[1]} using the schedule quantity {boq[2]}. Check the original BOQ template and retain the completed row. This is a schedule quantity, not a minimum hardware specification or a guaranteed order.'}
    # Never route mixed product tables or technical attributes as paperwork.
    if re.search(r'\b(?:RAM|GHz|GB|Graphics|Processor|mAh)\b', flat, re.I):
        return None
    for key, pattern, context, title, instruction in _RULES:
        if re.search(pattern, flat, re.I) and re.search(context, flat, re.I):
            return {'rule': key, 'title': title, 'instruction': instruction}
    return None


def interpretation_uncertain(condition):
    """Explicit uncertainty stays visible even when an action can be suggested."""
    return bool(condition.get('ambiguous') or condition.get('ambiguity_reason')
        or condition.get('quantity_conflict') or condition.get('unresolved_interpretations')
        or condition.get('confidence') in {'low', 'medium'}
        or (condition.get('requires_human_review') and not condition.get('review_reasons'))
        or any(re.search(r'\b(?:ambiguous|uncertain|conflicting|contradictory|uncertainty)\b', note, re.I)
               for note in condition.get('review_reasons', [])))


def literal_action(text):
    """Resolve only the next action, never mandatory status or submission success.

    Full-clause patterns avoid treating a keyword inside a conditional or a
    combined requirement as a complete instruction. Original uncertainty stays
    stored and still blocks readiness through the unapproved assessment.
    """
    flat = re.sub(r'^\s*\d+(?:\.\d+)*\.?\s+', '', ' '.join(text.split()))
    patterns = (
        (r'Prospective bidders are accordingly advised to go through instructions provided at Central Public Procurement Portal;?',
         'Read the CPP Portal instructions', 'Read the referenced portal instructions and record completion. The word advised is retained; no mandatory obligation is inferred.'),
        (r'Tenderer/Bidders are advised to follow the instructions provided in the [‘\']Instruction to Tenderer[’\'] specified at Annexure-III of this Tender document for e-submission of the bids online through Central Public Procurement Portal Website: https?://eprocure\.gov\.in/eprocure/app before proceeding with the tender;?',
         'Read Annexure III before preparing the bid', 'Read Annexure III and the referenced portal instructions. Keep a checklist; this does not prove a bid has been submitted or infer that advisory wording is mandatory.'),
        (r'Financial bid as per Annexure II of this tender document \.xls',
         'Prepare the Annexure II XLS file', 'Use the original Annexure II XLS template and retain the completed file. Check its cover placement before submission; a PDF is not a substitute for the XLS file.'),
        (r'Critical Dates:\s*-? Given in page one of the Tender document',
         'Open page one and confirm the schedule', 'Read the dates on page one and check subsequent amendments. Record the applicable schedule. No date or deadline is inferred from this cross-reference.'),
        (r'More information useful for submitting online bids on the CPP Portal may be obtained at: https?://eprocure\.gov\.in/eprocure/app\s*\.',
         'Read the linked CPP bidding guidance', 'Read the guidance at the URL quoted below. This is an information-reading task, not evidence of portal submission.'),
    )
    for pattern, title, instruction in patterns:
        if re.fullmatch(pattern, flat, re.I):
            return {'rule': 'literal_source_action', 'title': title, 'instruction': instruction}
    return None
