# Feedback on Nebius Token Factory and NVIDIA Nemotron

This feedback is based on TenderReady's implementation and real local acceptance runs recorded on 29 October 2026. It describes our experience with synthetic procurement documents, not a general model benchmark. See the [live verification notes](live-verification.md) and [setup instructions](../README.md#run-locally).

## What we used

| Technology or service | Actual use in TenderReady |
|---|---|
| Nebius Token Factory | Hosted inference through its OpenAI-compatible API; account model discovery; real requirement-extraction calls. |
| NVIDIA Nemotron 3 Super | Earlier live extraction using `nvidia/nemotron-3-super-120b-a12b`. |
| NVIDIA Nemotron 3 Ultra | Current configured model, `nvidia/Nemotron-3-Ultra-550b-a55b`, confirmed in our account catalog and exercised in live extraction. |
| Nebius AI Cloud | CPU VM hosting the HTTPS frontend, backend and private document/database storage; deployed and tested on 30 October 2026. |
| Serverless Endpoints and Serverless Jobs | Not used; no hands-on evaluation claimed. |
| Other NVIDIA tools or frameworks | Not integrated or evaluated in this MVP. |

Initial tests ran locally. On 30 October 2026 the frontend, FastAPI application, database and private document storage were deployed to Nebius AI Cloud, while Token Factory continued to provide hosted inference. Cloud billing activation was separate from Token Factory setup; the CPU VM allowed deployment without self-hosting model weights.

## What worked well

- **Hosted inference reduced infrastructure work.** We could connect our backend to Nemotron without provisioning GPUs, downloading model weights or running our own inference server. This let us focus on source citations, evidence checks and amendment propagation. We did not measure hours saved or compare hosting costs.
- **One integration supported both tested models.** Model discovery and server-side configuration let us select account-available Super and Ultra models without changing the supplier UI or exposing the provider key to the browser. Switching models still required validation of their output formats.
- **The models produced useful structured extraction in the tested scenario.** Real calls extracted a mandatory minimum of 32 GB RAM from page 2 of a synthetic tender. The application validated the quotation and page reference before persisting the requirement. Our deterministic engine then identified the conflict with the supplier's 16 GB RAM; that compliance comparison was performed by application code, not certified by the model.
- **Usage metadata supported traceability.** Successful calls returned token usage that we stored with model identifiers, timestamps and outcomes. This made it possible to distinguish real provider runs from offline samples and inspect the provenance of an extraction.

## Friction we observed and how we handled it

During the Ultra acceptance run, a numeric condition included `GB RAM` in its unit field instead of the standalone `GB` expected by our original validator. Earlier acceptance attempts exposed this compatibility mismatch. We clarified the extraction prompt and added a bounded normalization rule that requires the compound unit and attribute to agree with the exact source quotation. Unsupported or ambiguous units remain subject to review. This was an integration issue with our expected format, not evidence that the underlying numeric requirement was necessarily wrong.

A plausible structured response is not sufficient evidence of correctness. We retained strict JSON/schema validation, exact source checks, deterministic comparisons and human review for uncertainty. General accuracy across arbitrary tender PDFs, scanned documents and complex procurement language has not been established by these small synthetic tests.

Our automated tests also exercise malformed responses, timeouts, rate limits and provider errors using test transports. Those tests verify application error handling; they are not evidence that all of those failures occurred against the live service, or a measurement of provider reliability.

## Suggested improvements

1. **More source-grounded extraction examples.** A procurement-style cookbook example with exact page quotations, separate numeric value/unit/attribute fields, explicit ambiguity flags and strict validation would help teams building review-sensitive workflows.
2. **Clear per-model output-format guidance.** Examples for the exact catalog identifiers, including structured-output configuration, completion limits and possible formatting differences when switching models, would reduce integration trial and error. This is a suggestion based on our integration needs, not a claim that existing documentation has no such guidance.
3. **End-to-end diagnostic examples.** A reference flow combining catalog discovery, a small authenticated extraction, safe error handling and persisted usage would help distinguish missing configuration, provider failures and locally rejected output without logging secrets.

## Evaluation limits

These are observations from a local MVP and synthetic acceptance tests. We make no measured claims about throughput, latency improvements, cost savings, general extraction accuracy or Ultra being superior to Super. We did not benchmark self-hosted inference or evaluate Serverless services; AI Cloud evaluation is limited to this single-VM deployment. No model output establishes document authenticity, legal eligibility or a contract award; final findings remain reviewable by a person.
