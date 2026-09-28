# Railway Infrastructure as Code

This repository defines a three-service project:

- **API** — FastAPI (`python -m app.main`), healthcheck `/healthz`, pre-deploy `python -m app.migrate`
- **Worker** — Procrastinate (`python -m app.worker`), healthcheck `/healthz`
- **Postgres** — managed database; API and Worker reference `DATABASE_URL` over the private network

## Plan and apply

```bash
npm install railway
railway login
railway link
railway config plan
railway config apply
```

`railway.toml` and `railway.worker.toml` at the repo root are the same start/healthcheck settings for the marketplace Template Composer (or legacy Config as Code). New services should use this file instead.

Do not add `package.json` at the repository root — Railpack would then detect a Node app.
