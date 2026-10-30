# Nebius VM deployment

Frontend and FastAPI run in one non-root container, behind Caddy HTTPS.
The current hostname is configured in `Caddyfile`; change it and the server
`CORS_ORIGINS` together when moving to a custom domain. The current VM IP is
dynamic: preserve the VM/IP or update DNS and configuration after changes.

## Private configuration

`/opt/tenderready/server.env` is root-owned, mode 0600, outside the source tree.
Set APP_ENV=production, APP_API_TOKEN (at least 32 random characters),
NEBIUS_API_KEY, NEBIUS_BASE_URL, NEBIUS_MODEL, DATABASE_URL,
STORAGE_DIR, and CORS_ORIGINS (JSON array of HTTPS origins).
Never put server.env or keys in Git, Docker images, or frontend variables.

The app currently uses a shared operator access token, not separate user accounts.
Only trusted reviewers should receive it. Enter it in the workspace Application
access panel. Anyone holding it can access the deployment's workspaces.

## Start or update

From `/opt/tenderready/app`:

```sh
sudo docker compose -f deploy/compose.production.yaml up -d --build
sudo docker compose -f deploy/compose.production.yaml ps
```

Migrations run before startup. SQLite and PDFs persist in `/opt/tenderready/data`;
this directory must be owned by uid 10001, mode 0700. Do not delete volumes/data
when updating. Only ports 80/443 are published; the backend and database are private.

## Backup before updates

For a consistent database/PDF backup, stop the app briefly, archive the data to a
private root-owned directory, then restart. Store a separate encrypted off-VM copy
for disaster recovery. Local backups alone do not protect against VM loss.

```sh
sudo install -d -m 700 /opt/tenderready/backups
sudo docker compose -f deploy/compose.production.yaml stop app
sudo sh -c 'umask 077; tar -czf /opt/tenderready/backups/data-$(date -u +%Y%m%dT%H%M%SZ).tgz -C /opt/tenderready data'
sudo docker compose -f deploy/compose.production.yaml start app
```

## Verify

Check HTTPS `/`, `/api/health`, authenticated `/api/ready`, workspace creation,
PDF upload and source access. Unauthenticated `/api/workspaces` must return 401;
`/.env`, `/server.env`, and `/data/tenderready.db` must return 404.
Run a synthetic extraction only when testing provider integration is intended;
it consumes Token Factory credits. Do not present cached/demo output as live AI.
