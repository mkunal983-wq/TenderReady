# Nebius deployment verification — 2026-10-30

Public URL: https://tenderready.213.239.171.132.sslip.io/
VM: tenderready-web, computeinstance-e04cc24hvnjxtr2901, eu-west2.
Two vCPUs, 8 GiB, Ubuntu 24.04, encrypted 64 GiB disk.

## Verified live

- HTTPS homepage 200; Docker frontend/API and Caddy running.
- Authenticated readiness reports database ready.
- Workspace creation, PDF parsing/upload, and source page 1 persisted.
- Real Token Factory extraction: nvidia/Nemotron-3-Ultra-550b-a55b;
  model-run succeeded, 894 input + 809 output tokens, 4309 ms.
- Exact source requirement: The offered laptop must have at least 32 GB RAM.
- Numeric condition: >= 32 GB; source PDF page 1.
- Replacement datasheet with separate Model and RAM lines: observed 16 GB;
  result conflicting. Previous assessments retained (3 records).
- Fixed generic adjective “offered” incorrectly being treated as a model ID;
  regression coverage also covers proposed, supplied and required.
- Source PDF: authorized 200, anonymous 401. Workspace list anonymous 401.
- /.env, /server.env, /data/tenderready.db, /backend/.env return 404.
- Both CSV exports 200; saved data survived app container replacement.
- Server environment file mode 0600; no secrets included in source archive.

## Validation commands

- npm test: 46 passed.
- npm run lint: passed.
- npm run build (includes tsc --noEmit): passed.
- python -m pytest tests/test_check_planning.py -q: 104 passed.
- python -m ruff check src tests: passed.
- Full backend suite before final adjective fix: 528 passed (5 warnings).
- Full suite after fix: 532 passed, 5 deprecation warnings, in 101.38 seconds.

## Limitations

Shared app access token: trusted operator/reviewers only; no per-user isolation.
Live storage starts separately; local historical workspaces were not migrated.
Tender sample remains draft; no human approval or bid-ready claim was made.
Single-line unlabeled/compound evidence can require human review. Product identity
and extraction review notes remain review items when not established.
Hostname uses dynamic VM IP and sslip.io; custom domain/static IP is advisable.
After explicit user approval, a root-only private backup was created on the VM.
Backup SQLite integrity passed and all three document hashes matched. The app
was restarted and HTTPS, authenticated workspace/PDF access and both exports
passed again. Off-VM disaster-recovery backup is not configured.
