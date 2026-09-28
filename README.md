# Deploy and Host FastAPI + Procrastinate on Railway

[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/new)

Postgres-native background jobs for Python 3.12. FastAPI enqueues, a Procrastinate worker drains the same Postgres, and there is no Redis. Healthcheck: `GET /healthz` (200 even when the queue is empty).

## About Hosting FastAPI + Procrastinate

This template runs three services in one Railway project:

1. **API** — FastAPI + uvicorn. `POST /jobs/demo` inserts a job. `GET /healthz` binds `PORT` and returns 200 before any job exists.
2. **Worker** — `python -m app.worker` (or `procrastinate --app=app.tasks.procrastinate_app worker`). Same repo, different start command. Serves `/healthz` on `PORT` so Railway has a liveness probe.
3. **Postgres** — app data and Procrastinate job tables on the private network (`*.railway.internal`). Volume stays on Postgres only.

Railpack builds Python from `.python-version` and `RAILPACK_PYTHON_VERSION=3.12`. First deploy applies the job schema with Alembic (`python -m app.migrate`) and an idempotent `procrastinate` schema apply if the tables are missing.

Procrastinate is the Postgres-native queue. Celery/Huey/RQ templates exist on the marketplace; this one exists so you do not add Redis to get a worker.

## Why Deploy FastAPI + Procrastinate on Railway

Railway is a singular platform to deploy your infrastructure stack. Railway will host your infrastructure so you do not have to deal with configuration, while allowing you to vertically and horizontally scale it.

By deploying this stack on Railway you get a public API, a private worker, and private Postgres in one project. The Python 3.12 pin avoids the Railpack default 3.13 (PEP 594 / removed stdlib modules). The connect helper prefers IPv6 for `*.railway.internal` so asyncpg and SQLAlchemy do not hang on a dead IPv4 A record.

## Common Use Cases

- SaaS backends that enqueue email, webhooks, or reports without standing up Redis
- FastAPI apps that need a real worker process (not `BackgroundTasks` in the web replica)
- A 3.12-pinned starter when Railpack 3.13 breaks an older lockfile
- Python services that talk to private-network Postgres (asyncpg / psycopg / SQLAlchemy)

## Dependencies for FastAPI + Procrastinate Hosting

- Python 3.12 (`.python-version`, `railpack.toml`, `RAILPACK_PYTHON_VERSION=3.12`)
- FastAPI + uvicorn
- [Procrastinate](https://procrastinate.readthedocs.io/en/stable/) 3.10 (`PsycopgConnector`, psycopg v3)
- asyncpg + SQLAlchemy 2.0 for app queries and the IPv6-safe connect helper
- Alembic (first deploy creates `procrastinate_*` tables)
- Railway Postgres (private `DATABASE_URL`)

### Deployment Dependencies

- [Procrastinate](https://github.com/procrastinate-org/procrastinate)
- [FastAPI](https://fastapi.tiangolo.com/)
- [Railway private networking](https://docs.railway.com/private-networking) (`*.railway.internal`, dual-stack / IPv6)
- [PEP 594](https://peps.python.org/pep-0594/) (stdlib modules removed in 3.13)
- [Railway Infrastructure as Code](https://docs.railway.com/infrastructure-as-code) (`.railway/railway.ts`)

### Implementation Details

API start:

```bash
python -m app.main
```

Worker start (separate service, same image/repo):

```bash
python -m app.worker
```

The worker process binds `DATABASE_URL` through the IPv6-safe helper before it opens Procrastinate. Prefer `python -m app.worker` on Railway. The CLI (`procrastinate --app=app.tasks.procrastinate_app worker`) does not run that helper.

Enqueue a demo job (2 second sleep + log line):

```bash
curl -sS -X POST https://$RAILWAY_PUBLIC_DOMAIN/jobs/demo \
  -H 'content-type: application/json' \
  -d '{"seconds": 2, "message": "hello"}'
```

If `JOB_API_TOKEN` is set, send `Authorization: Bearer $JOB_API_TOKEN`. You can generate one with `${{ secret() }}` in the service variables.

### Why Deploy FastAPI + Procrastinate on Railway?

Railway is a singular platform to deploy your infrastructure stack. Railway will host your infrastructure so you do not have to deal with configuration, while allowing you to vertically and horizontally scale it. By deploying FastAPI + Procrastinate on Railway, you are one step closer to supporting a complete full-stack application with minimal burden. Host your servers, databases, AI agents, and more on Railway.

## Deploy

1. Create a Railway project with **Postgres**, **API**, and **Worker**.
2. Point API and Worker at this GitHub repo (same root, no monorepo split).
3. API settings: start `python -m app.main`, pre-deploy `python -m app.migrate`, healthcheck `/healthz`, config file `railway.toml` (or the same values in `.railway/railway.ts`).
4. Worker settings: start `python -m app.worker`, healthcheck `/healthz`, config file `railway.worker.toml`. Do not give the worker a public domain unless you want the probe URL public.
5. On **both** API and Worker set:

   ```text
   RAILPACK_PYTHON_VERSION=3.12
   DATABASE_URL=${{Postgres.DATABASE_URL}}
   ```

   Prefer the private host if your plugin still exposes a public URL as `DATABASE_URL`:

   ```text
   DATABASE_URL=postgresql://${{Postgres.PGUSER}}:${{Postgres.PGPASSWORD}}@${{Postgres.RAILWAY_PRIVATE_DOMAIN}}:5432/${{Postgres.PGDATABASE}}
   ```

   Optional:

   ```text
   JOB_API_TOKEN=${{ secret() }}
   ```

6. Attach a volume only on Postgres (the managed plugin does this). Do not add volumes to API or Worker.
7. Give the API a public HTTP domain. Open `/` or `GET /healthz`.
8. `POST /jobs/demo`, then watch Worker logs for `demo job started` / `demo job finished`.

## Local run

Python 3.12 and a Postgres reachable at `DATABASE_URL`. Compose (optional):

```bash
docker compose up -d postgres
cp .env.example .env
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m app.migrate
```

Terminal 1 — API (uncommon port so it does not collide with 3000/8080):

```bash
set -a && . ./.env && set +a
python -m app.main
```

Terminal 2 — worker:

```bash
set -a && . ./.env && set +a
python -m app.worker
```

```bash
curl -sS http://127.0.0.1:43122/healthz
curl -sS -X POST http://127.0.0.1:43122/jobs/demo \
  -H 'content-type: application/json' \
  -d '{"seconds": 1, "message": "local"}'
curl -sS http://127.0.0.1:43122/jobs
```

`GET /healthz` is 200 even when Postgres is down. `GET /readyz` and `POST /jobs/demo` return 503 until the database is reachable.

## Healthcheck

| Service | Path | Behavior |
|---|---|---|
| API | `GET /healthz` | Always 200 once the process binds `PORT`. Empty queue is fine. Missing `DATABASE_URL` is fine. |
| API | `GET /readyz` | 200 only if Postgres answers `SELECT 1`. |
| Worker | `GET /healthz` | 200 after the worker has opened Procrastinate and can ping Postgres. 503 while starting. Bind `0.0.0.0:$PORT` (not `::`). |

## Private network, asyncpg, and Python 3.12

**Private DNS is IPv6-first.** Legacy Railway environments resolve `*.railway.internal` to IPv6 only. Newer environments (after 16 Oct 2025) are dual-stack. asyncpg and SQLAlchemy’s asyncpg dialect often try the IPv4 A record first, hang, and never try AAAA. This repo resolves the host with `AF_UNSPEC`, prefers IPv6 for `*.railway.internal`, and passes a **bare IP** as `host=` kwargs. Do not put a raw IPv6 literal back into a URI — asyncpg has mis-parsed `[v6]:port`.

**Private Postgres has no TLS.** `sslmode=disable` on `*.railway.internal`. Public `*.rlwy.net` proxies use `sslmode=require`. The helper infers this from the hostname.

**DNS can be empty at boot.** `fd12::10` may return NXDOMAIN for a few seconds after the container starts. The helper retries. Do not resolve `DATABASE_URL` at import time.

**Bind `0.0.0.0`, not `::`.** Python’s asyncio sets `IPV6_V6ONLY` on `::`, so uvicorn on `::` is IPv6-only. Railway healthchecks and the public edge often arrive over IPv4 and the replica never becomes healthy.

**Pin Python 3.12.** Railpack defaults to 3.13. Set `.python-version`, `railpack.toml`, and `RAILPACK_PYTHON_VERSION=3.12` on every Python service.

**Volumes are not backups.** Only Postgres needs a volume. Redeploying API/Worker must not depend on local disk.

**Config as Code is deprecated.** `railway.toml` still documents the API/worker start commands. New services should use `.railway/railway.ts`. Hard cutoff for CaC: 2026-12-01.

## Source

https://github.com/bhanuvadlakonda/fast-queue

## Layout

```text
app/main.py      FastAPI (enqueue + /healthz)
app/worker.py    Procrastinate worker + /healthz
app/tasks.py     Procrastinate App + demo_sleep
app/db.py        IPv6-safe asyncpg / SQLAlchemy / psycopg helper
app/migrate.py   Alembic upgrade + schema safety net
.railway/railway.ts
railway.toml
railway.worker.toml
```
