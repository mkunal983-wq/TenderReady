/** Display copy only. API values, source quotes, and saved history stay unchanged. */
function label(value: string, labels: Record<string, string>) {
  return labels[value] ?? value.replaceAll('_', ' ');
}

export function categoryLabel(value: string) {
  return label(value, {
    product_identity: 'Product details', bidder_identity: 'Company details',
    validity_date: 'Dates and deadlines', numeric_threshold: 'Number or amount',
    required_information: 'Required documents or details', manual_review: 'Check manually',
  });
}
export function obligationLabel(value: string) {
  return label(value, { mandatory: 'Required', optional: 'Optional', unclear: 'Check if required' });
}
export function statusLabel(value: string) {
  return label(value, { reference_only: 'Reference information', action_required: 'Task to complete', not_checked: 'Not checked', supported: 'Supported by evidence', inconclusive: 'Needs review',
    conflicting: 'Details do not match', missing: 'Missing evidence', outdated: 'Out of date' });
}
export function reviewStateLabel(value: string) {
  return label(value, { awaiting_review: 'Waiting for review', approved: 'Approved', rejected: 'Rejected',
    reopened: 'Needs another review', corrected: 'Corrected' });
}
export function numericOperatorLabel(value: string) {
  return label(value, { '>=': 'At least', '<=': 'At most', '>': 'More than', '<': 'Less than',
    '=': 'Exactly', unspecified: 'Number stated; check how it applies' });
}
export function dateRelationLabel(value: string) {
  return label(value, { on: 'On this date', before: 'Before', after: 'After',
    on_or_before: 'On or before', on_or_after: 'On or after', valid_through: 'Valid until',
    relative: 'Timing depends on an event or period', unspecified: 'Timing needs review',
    at_event: 'When this event happens', event: 'When it is needed', repeating_period: 'Period to check' });
}

// Exact known system messages only: never apply a word replacement to tender
// clauses, source excerpts, reviewer comments, filenames, or other user text.
const messages: Record<string, string> = {
  'Evidence review only. This is not a guarantee of legal eligibility, bid acceptance, document authenticity, or contract award.':
    'This helps you check documents. It does not prove they are genuine, confirm you can bid, or guarantee that your bid will be accepted or win.',
  'No evidence assessment has been recorded.': 'No documents have been checked for this requirement yet.',
  'Evidence, dates, or tender assumptions changed; rerun verification.': 'The documents, dates, or tender details changed. Run the checks again.',
  'Mandatory or optional status is unclear; review the tender interpretation.': 'It is not clear whether this is required. Check the original tender.',
  'Publish a reviewed tender baseline before completing evidence review.': 'Review the tender requirements, then save the starting tender version in Amendments.',
  'No active requirements have been established.': 'No requirements are ready to check yet.',
  'Optional requirements still need human review; record how they will be handled.': 'Review the optional requirements and record what you will do about them.',
  'Open corrective tasks remain on current mandatory or unclassified requirements.': 'Some required items, or items that may be required, still have unfinished tasks.',
  'The guarantee is due at the delivery event, not on-or-after an inferred calendar date. No calendar deadline is invented.':
    'Submit the guarantee when the goods are delivered. This clause does not give a calendar date.',
  'The source combines an upper-duration phrase with a delivery event. No minimum validity or calendar expiry is inferred; clarification is required.':
    'The wording about how long the guarantee stays valid is unclear. Ask the buyer to confirm the period. No expiry date has been assumed.',
  'Preserved the written currency and amount for each stated year. The reference date and financial-year boundaries are unspecified; no aggregate or invented calendar years are used.':
    'The turnover amount applies to each stated year, not all years added together. The exact years are not given here; confirm which years to use.',
  'Restored the complete same-page procedural clause, including its continuation; verify the full source before approval.':
    'The rest of this instruction was found on the same page and added here. Read the full instruction before approving it.',
  'Scanning resolution is optional advice ("may be scanned"), not a supplier acceptance threshold. Example file formats are not made mandatory by this clause.':
    'The scan quality is a suggestion, not a required limit. The file formats listed here are examples; check the upload checklist for required formats.',
  'USB version identifiers are not numerical measurement units. Original port specification is retained; count/version mapping needs review.':
    'USB 2.0 and 3.0 are USB versions. Check how many ports of each version are required in the original tender.',
  'This passage describes portal behavior or provides issuing-authority/helpdesk reference information; it is not a supplier evidence or product threshold.':
    'This is information about the bidding website or its contact details. It is not a requirement for your product or company documents.',
  'The source says "advised" without a mandatory cue. No mandatory obligation is inferred from model-generated rationale.':
    'The tender gives advice here. It does not clearly say this is required.',
  'Overlapping fragments were consolidated into the same complete source clause; original versions remain in history.':
    'These text fragments belong to one instruction and are now shown together. The earlier records are still saved.',
  'Recovered an explicit financial-bid file-format checklist row; review its cover context before submission.':
    'A missing financial-bid upload instruction was found in the checklist. Check which bid section it belongs to.',
  'Quantity recovered by deterministic source reconciliation; review the stated scope and schedule before use.':
    'This quantity was read from the original table using fixed rules. Check the product and quantity before using it.',
  'Anticipated quantity is not a guaranteed order or a minimum threshold.':
    'This is the estimated quantity. It is not a guaranteed order or a minimum requirement.',
  'BOQ schedule quantity is not a minimum product threshold or a guaranteed purchase.':
    'This quantity comes from the price table. It is not a minimum product specification or a guaranteed order.',
  'Source quantity references disagree for this product scope; human review must resolve the discrepancy.':
    'Different parts of the tender give different quantities for this product. Check with the buyer before choosing a quantity.',
  'Quantity cell is absent, zero, or outside supported bounds; human review is required.':
    'The quantity is missing, zero, or cannot be read safely. Check the original table.',
  'Product configuration scope comes from the cited table heading; confirm applicability before evidence verification.':
    'The table heading shows which product option this requirement belongs to. Check that the company document covers that same option.',
  'Numeric condition has a version-like unit; review its meaning before using it as a threshold.':
    'This number may be a product or software version. Check its meaning before using it as a limit.',
  'Explicit obligation wording could not be validated.': 'Check the tender to confirm whether this item is required.',
  'Model reports uncertainty; verify against the source.': 'The AI is unsure. Check the original PDF.',
  'Whitespace-only alignment restored exact source formatting; human review is required.':
    'Spacing was matched to the original PDF. Please check the text.',
  'This extraction has unresolved interpretation issues. Review and correct its source-backed criteria before relying on evidence checks.':
    'Some requirement details are still unclear. Check them against the tender and correct the checks before relying on the result.',
  'This clause belongs to a particular tender configuration. Review the cited product scope and its evidence assignment; a global numeric match is insufficient.':
    'This requirement applies to one product option. A matching number alone is not enough; check that the document covers the right option.',
  'No supported check specification. Review the requirement and define source-backed criteria.':
    'No checks are set up yet. Read the requirement and add checks using its exact wording.',
  'A human must confirm that these criteria cover the entire requirement, including document purpose and scope.':
    'Confirm that the checks cover the whole requirement and that each document is for the right purpose and product.',
  'An extracted condition has no corresponding source-backed check; review and add a suitable criterion.':
    'Part of this requirement has no check yet. Review it and add a matching check.',
  'Unsupported units, date format, or ambiguous value.': 'The value, unit, or date format is unclear. Check the document.',
  'The document gives conflicting values for the same field; no value was selected silently.':
    'The document gives different values for the same detail. Check which is correct; none was chosen automatically.',
  'No explicit bidder field; legal-entity scope needs review.': 'The company name could not be read clearly. Check that the document names your company.',
  'Exact legal-name comparison to the workspace supplier (case and whitespace normalized only).':
    'The company name was compared with the name in this workspace. Only spaces and capital letters were ignored.',
  'Expected product/model identity is not unambiguously established for this requirement.':
    'The required product model is not clear. Check the tender and company document.',
  'Reference-only text is not a supplier compliance requirement.': 'This is reference information, not a requirement to check.',
  'This interpretation was superseded. Verify its current revision.': 'This requirement has been updated. Open and check the latest version.',
  'Criterion quotation must occur exactly in this requirement and its source.': 'Copy the check text exactly from this requirement and the original PDF.',
  'Expected value must occur in the criterion quotation.': 'The required value must appear in the tender text you quoted.',
  'Unsupported expected value. Use explicit GB, INR, or ISO date values.': 'Use a value with GB or INR, or enter the date as YYYY-MM-DD.',
  'Published tender history is immutable. Upload a revised tender for new interpretation.': 'This tender version is already saved. Upload a new version to change its requirements.',
  'Published interpretations are immutable; upload a new version.': 'These requirements are already saved. Upload a new tender version to change them.',
  'Complete extraction before reconciling cached results.': 'Read the requirements from the PDF first, then update the saved results.',
  'Correction could not be grounded in its source page; review manually.': 'The update could not be matched to the original page. Check the PDF yourself.',
  'Repeated source passage has ambiguous offsets; review manually.': 'This text appears more than once. Check the PDF to choose the right passage.',
  'A corrected condition is not supported by its source excerpt.': 'The updated condition does not match the quoted PDF text. Please review it.',
  'A corrected value is not literal source text; review manually.': 'The updated value was not found in the original text. Please check the PDF.',
  'Excerpt must occur exactly on the selected source page.': 'Copy the text exactly from the selected PDF page.',
  'NEBIUS_API_KEY is not configured on the server.': 'AI is not set up yet. Ask the app owner to add the Nebius API key on the server.',
  'Token Factory model discovery failed; check credentials and connectivity.': 'Could not connect to Nebius. Ask the app owner to check the API key and connection.',
  'Token Factory rate limit reached after bounded retries. Wait before retrying.': 'Nebius is receiving too many requests. Wait a little, then try again.',
  'Token Factory authentication failed. Check the server-side API key.': 'Nebius did not accept the API key. Ask the app owner to check the key on the server.',
  'Configured Nemotron model is unavailable to this account. Check NEBIUS_MODEL.': 'This Nebius account cannot use the selected AI model. Ask the app owner to check the model setting.',
  'Configured Nemotron model is not available to this account.': 'This Nebius account cannot use the selected AI model. Ask the app owner to check the model setting.',
  'Token Factory request failed; check model access and quota.': 'Nebius could not complete the request. Check model access and available credits.',
  'Token Factory returned no completion.': 'Nebius returned no result. Please try again.',
  'Invalid application token': 'The app access key was not accepted. Check it and try again.',
  'Unauthenticated development access is restricted to loopback.': 'Remote access needs an app access key. Ask the app owner to set it up.',
  'Database migrations are not current. Run alembic upgrade head.': 'The database needs an update. Ask the app owner to run alembic upgrade head on the server.',
  'Database unavailable or migrations not applied': 'The database is not ready. Ask the app owner to check the connection and database setup.',
  'This evidence version has already been replaced. Select its current version.': 'This document was already replaced. Select its latest version.',
  'Replacement must have the same evidence type as the original.': 'Choose the same document type as the file you are replacing.',
  'Evidence or the assessment date changed since this assessment. Rerun verification before approving or correcting.':
    'The documents or check date changed. Run the checks again before approving or correcting this result.',
};

export function plainSystemText(value: string): string {
  if (messages[value]) return messages[value];
  const count = value.match(/^(\d+) mandatory or unclassified requirements remain unresolved\.$/);
  if (count) return `${count[1]} required items, or items that may be required, still need attention.`;
  const pending = 'Unapplied tender documents require review: ';
  if (value.startsWith(pending)) return `Tender files waiting for review: ${value.slice(pending.length)}`;
  const review = value.match(/^The current finding requires human approval; review state: ([a-z_]+)\.$/);
  if (review) return `Someone needs to review this result. Current status: ${reviewStateLabel(review[1])}.`;
  return value;
}
