# Real Nebius / Nemotron verification

Verified locally on 29 October 2026 with synthetic, non-private PDFs. This was a real provider run, not a mocked transport or the offline sample path.

- Endpoint: `https://api.tokenfactory.nebius.com/v1`
- Model: `nvidia/nemotron-3-super-120b-a12b`, confirmed in the authenticated account catalog.
- Tender: `samples/phase1a-live/tender-32gb.pdf`, page 2: "The product must have at least 32 GB RAM."
- Extracted condition: `>=`, value `32`, unit `GB`, mandatory, exact quotation and document/page reference persisted.
- Supplier evidence: `samples/phase1a-live/datasheet-16gb.pdf`, page 1: `RAM: 16 GB`.
- Deterministic outcome: **Conflict detected**. Required at least 32 GB; observed 16 GB.
- Both successful model runs persisted model identifier, timestamps, outcomes, duration and usage. Calls recorded 1,196 / 206 and 1,174 / 1,061 input / output tokens respectively.
- The existing Requirements UI displayed the requirement, page-2 PDF source and conflict rationale. The finding remains awaiting human review; the draft baseline was not automatically approved or published.

Commands executed from `backend/` using the project virtual environment:

```sh
python -m tenderready.cli models
python scripts/live_ram_acceptance.py
python -m pytest -q
python -m ruff check src tests scripts
```

Results: live acceptance exit 0; **183 backend tests passed** in 45.99 seconds with three upstream deprecation warnings; lint passed. No frontend source changes were required for this live run. Earlier frontend verification: 23 tests passed, lint, typecheck and production build passed.

To reproduce, configure your own key privately with `python backend/scripts/configure_nebius_key.py`, verify your account's model catalog, restart the backend, and run the commands above. Inference consumes provider credits. Missing credentials produce a blocked status, never a fabricated successful run.

This verifies the stated synthetic acceptance scenario, not arbitrary PDF accuracy or production readiness. Evidence parsing remains limited to explicit labelled facts. Product scope, ambiguous clauses, source authenticity and approvals still require human review. No keys, database copies, private uploads or account billing data are included in this repository.

## Nemotron Ultra 550B

The default model was switched to `nvidia/Nemotron-3-Ultra-550b-a55b` on 29 October 2026 after confirming availability in the authenticated account catalog. The same real PDF acceptance test passed: a mandatory minimum of 32 GB RAM on page 2 conflicted with 16 GB evidence on page 1. Two successful Ultra calls persisted usage of 1,232 / 427 and 1,216 / 944 input / output tokens.

Ultra can preserve an attribute in `unit_text`, for example `GB RAM`. The deterministic verifier now accepts only bounded GB-plus-attribute forms that occur in the source quote and match the independently parsed RAM/storage field. It retains the raw model extraction, refuses ambiguous or unsupported units, and never uses semantic similarity as proof. Earlier extraction attempts are preserved; their initial acceptance failures exposed this format mismatch. The extraction prompt now requests a standalone measurement unit, and the live acceptance script also asserts that the backend actually used the configured model.

After the compatibility fix: **189 backend tests passed**, with three upstream deprecation warnings. No database migration or frontend source change was needed. Human review and product-scope checks remain required. Set `NEBIUS_MODEL` on the server to select an account-available model; historical Super and Ultra run records retain their original model identifiers. No relative performance or cost advantage was established by this small test.
