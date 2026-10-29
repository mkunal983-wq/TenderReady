# TenderReady

[MIT License](LICENSE) · [Setup and running](#run-locally) · [Nebius and NVIDIA feedback](docs/feedback.md)

**Amendment-aware procurement evidence review.**

TenderReady connects tender requirements to supplier evidence, identifies which findings and approvals are affected by an amendment, and coordinates targeted reassessments with a preserved audit trail. Humans retain control over coverage confirmation and final review decisions.

Built for small IT hardware suppliers preparing school and university procurement bids. Hackathon track: **Best Apps and Agents**.

> **Current status:** the local supplier workflow and **real NVIDIA Nemotron inference through Nebius Token Factory were verified on 29 October 2026**. A synthetic tender requiring 32 GB RAM was extracted with an exact page-2 citation, then deterministic verification rejected 16 GB supplier evidence. Two successful provider calls and their usage metadata were persisted. The offline sample remains separately labelled and never pretends to be an AI run. See [live verification](docs/live-verification.md).

## What works

- Create, rename and soft-delete tender workspaces, with deletion confirmation.
- Upload versioned text-based tender PDFs and preserve exact source pages.
- Extract structured requirements through the configured Nemotron provider, with strict schemas, citation validation, safe errors and persisted model-run provenance.
- Upload datasheets, authorizations, certificates and project references; explicitly replace evidence without deleting earlier versions.
- Check model identity, bidder identity, explicit numeric thresholds, dates and required fields using bounded deterministic rules.
- Compare amendments as Added, Modified, Removed or Unchanged, reopen affected findings and retain unaffected approvals when their dependencies remain valid.
- Review findings, save comments, manage corrective tasks, inspect version/review history and export compliance-matrix and evidence-index CSV files.
- Use separate Requirements, Evidence Library, Amendments, Tasks and Export pages with real backend data.

Semantic similarity is never treated as proof of compliance. Evidence is not labelled officially verified without a trusted verification source. Readiness is an evidence-review state, not a guarantee of legal eligibility, authenticity, acceptance or award.

## Architecture

| Layer | Implementation |
|---|---|
| Frontend | React 19, TypeScript, Vite, Motion, PDF.js |
| Backend | FastAPI, Pydantic, SQLAlchemy |
| Database | SQLite locally; PostgreSQL configuration via Docker Compose |
| History | Versioned documents/requirements, scoped foreign keys, append-only review records |
| PDF parsing | pypdf in a bounded subprocess; page numbers preserved |
| AI | NVIDIA Nemotron through the OpenAI-compatible Nebius Token Factory API |
| Verification | Source-backed deterministic checks, explicit reviewer scope and uncertainty |

## Run locally

Use **Python 3.13** and **Node.js 24** to match the tested environment. From the repository root:

```sh
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.lock
python -m pip install --no-deps -e backend
cp .env.example .env
chmod 600 .env
```

For a quick local setup, edit the root `.env`:

```dotenv
DATABASE_URL=sqlite:///./tenderready.db
APP_ENV=development
APP_API_TOKEN=
NEBIUS_API_KEY=
```

Start the API from `backend/` so the relative SQLite path stays consistent:

```sh
cd backend
python -m alembic upgrade head
python -m uvicorn tenderready.api:create_app --factory --host 127.0.0.1 --port 8000 --no-proxy-headers
```

In another terminal, from the repository root:

```sh
cd frontend
npm ci
npm run dev
```

Open [http://127.0.0.1:5173](http://127.0.0.1:5173). Vite proxies `/api` to the local backend. API documentation: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

`npm run build` creates the frontend production bundle; it does not deploy or start the backend. A hosted deployment still requires an authenticated API and private persistent storage.

## Try the complete sample without an API key

1. Open Workspaces and select **Create sample workspace**.
2. The app uploads synthetic PDFs, extracts explicitly labelled clauses, stores clearly marked scripted sample approvals, and applies a RAM amendment from 16 GB to 32 GB.
3. Inspect the failed RAM check: required **32 GB**, evidence **16 GB**. Storage remains unchanged after this amendment.
4. Expand **Synthetic sample workspace · No AI inference** for a replacement datasheet and the remaining review steps.
5. Replace the original evidence, rerun affected checks, review the findings, resolve tasks and export both CSV files.

Every sample write uses the normal API and database. Sample reviews are marked `SYNTHETIC DEMO`. No fake provider output or successful model-run record is created.

For a repeatable real-HTTP acceptance check, run from `backend/` while the API is running:

```sh
python scripts/offline_acceptance.py
```

This creates a fresh sample workspace and checks missing evidence, wrong model, amendment propagation, unrelated approval preservation, replacement, task/review history and exports. The retained workspace is available in the existing UI.

Synthetic PDFs are in `samples/` and `frontend/public/samples/offline/`. The offline parser accepts narrow `Requirement ID:` blocks and explicit `Obligation: mandatory` or `Obligation: optional` lines; absent/ambiguous obligations are not invented.

## Enable NVIDIA Nemotron on Nebius

The provider key stays on the **server only**. Never put it in frontend environment variables, the browser's application-access-token field, chat, logs or a commit.

From the repository root, use the private terminal helper:

```sh
python backend/scripts/configure_nebius_key.py
```

The prompt hides the key and saves server configuration with owner-only permissions. Configure the official endpoint and an account-available model in `.env`:

```dotenv
NEBIUS_BASE_URL=https://api.tokenfactory.nebius.com/v1
# Confirm the exact model through account discovery before inference:
NEBIUS_MODEL=nvidia/Nemotron-3-Ultra-550b-a55b
NEBIUS_JSON_MODE=false
```

From `backend/`, with the venv active:

```sh
python -m tenderready.cli models
python -m tenderready.cli smoke
```

Use an exact NVIDIA Nemotron model ID returned by your account catalog. Restart the API after changing configuration. Then run the real PDF acceptance test:

```sh
python scripts/live_ram_acceptance.py
```

It makes actual provider calls using a fresh synthetic tender, verifies the 32 GB condition and source page against 16 GB evidence, and checks persisted successful model-run metadata. It consumes provider credits. Missing credentials return `BLOCKED/not_configured`, never a sample fallback. Account/model availability and model interpretation must genuinely pass before claiming working live inference.

Token Factory supplies requirement interpretation; the deterministic engine compares grounded facts and propagates changes. The implementation uses model discovery and `POST /v1/chat/completions`, strict response/citation validation, bounded retries and safe failure states. Token usage, model identifier, timestamps and operation outcomes are persisted without secrets. No measured speedup or credit savings are claimed yet.

References: [Token Factory API](https://docs.tokenfactory.nebius.com/api-reference/introduction), [Nebius Nemotron cookbook](https://github.com/nebius/token-factory-cookbook/tree/main/models/nemotron).

### How Token Factory accelerated development

Token Factory hosted the Nemotron inference used by our FastAPI backend, so we did not need to provision GPUs, download model weights or operate a model-serving stack. Its OpenAI-compatible API let us keep the provider integration in one server-side client and use the same application workflow for account-available Super and Ultra models. This reduced the infrastructure work needed to build and test requirement extraction, leaving development focused on citations, deterministic evidence checks and amendment history. This is a qualitative development benefit; we have not measured time savings, comparative model speed or cost savings.

**Services used:** Nebius Token Factory for NVIDIA Nemotron inference. The frontend, application backend, database and private document storage run locally in the verified setup. We have not used Nebius AI Cloud GPU instances, Serverless Endpoints or Serverless Jobs in this MVP, and do not claim deployment or hands-on feedback for those services. No other NVIDIA runtime or agent framework is integrated.

### Feedback on Nebius and NVIDIA

The hosted API and model catalog supported real Super and Ultra extraction tests, and returned usage metadata that we persisted for traceability. One observed integration issue was Ultra returning a compound unit such as `GB RAM`; we added source-checked normalization and retained human review for ambiguous outputs. More task-specific structured-extraction examples and clearer per-model output-format guidance would help developers building evidence-sensitive applications.

See [our detailed feedback](docs/feedback.md) for what worked, observed friction, suggested improvements and the limits of our evaluation. The [live verification notes](docs/live-verification.md) record the supporting tests.

## Automatic source-backed capacity amendments

Clear sentences such as `The Atlas A14 product must have at least 16 GB RAM.`
can now match the corresponding `32 GB` clause automatically. This bounded
parser accepts a complete mandatory sentence (`must/shall have`, `at least/at
most`, GB, RAM/memory/storage/SSD) with one grounded numeric condition. It masks
only the capacity and preserves every other word, including product identity.
Both sides must match uniquely. Similarity scores and model category labels do
not decide this mapping.

After the user previews and applies the amendment, the system transfers a
previously confirmed complete check specification only when it agrees with the
source and its shape is unchanged. Changed capacity checks rerun; valid
unaffected checks are reused. Prior approvals are reopened with an append-only
history entry, and new findings still await approval. Changed evidence forces a
fresh check rather than reuse. Duplicate clauses, uncertainty, alternatives,
negations, unrecognized units or extra conditions require review. This does not
provide arbitrary-prose auto-approval. No schema migration is required.

Regression coverage: `backend/tests/test_prose_amendments.py`. The amendment UI
also refreshes candidate mappings after asynchronous extraction without a reload.

## Tests

From `backend/`, with the virtual environment active:

```sh
python -m pytest -q
python -m ruff check src tests scripts migrations
python -m alembic check
python -m pip check
```

From `frontend/`:

```sh
npm run test
npm run lint
npm run typecheck
npm run build
```

Latest local verification on 29 October 2026: **212 backend tests and 24 frontend tests passed**, lint/typechecking/build passed, and the latest amendment change required no schema migration. Provider transport mocks occur only in automated tests and are not live-inference evidence. The offline acceptance path uses actual PDF parsing, persistence, checks and exports. Existing upstream deprecation/Motion build warnings are non-blocking.

## Configuration and boundaries

- `.env.example` documents limits and configuration. Root `.env`, then `backend/.env`, then process environment determine settings (environment wins).
- Default PDF limits: 10 MiB, 40 pages and 160,000 extracted text characters. Scanned-only and encrypted PDFs are rejected; no OCR is implemented.
- Evidence facts currently require explicit labelled formats such as `Model: Atlas A14`, `RAM: 16 GB`, and ISO validity dates. Arbitrary prose, tables, ambiguous units or identities require human review.
- Files are stored under private `data/documents/`; local databases and uploads are excluded from Git.
- Unauthenticated development access is restricted to loopback and trusted origins. Production mode requires an application token of at least 32 characters. This is single-operator access, not multi-user tenant isolation; reviewer names are labels, not independently authenticated identities.
- Analysis currently uses one API process. Interrupted jobs become retryable failures on restart; a durable distributed worker is not implemented.
- Evidence replacement conservatively stales checks using the affected evidence category. Original documents, assessments and reviews remain preserved.
- PostgreSQL/Docker configuration is included but was not re-verified in the latest local audit. Public hosting, OCR, cross-workspace supplier libraries and a demo video remain separate work.

For local PostgreSQL, configure a strong `APP_API_TOKEN` and run `docker compose up --build -d`. The provided development database credentials must be replaced before any production deployment. Compose binds ports to loopback and runs migrations before the API.

## License

[MIT](LICENSE).
