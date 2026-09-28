import { defineRailway, group, postgres, project, service } from "railway/iac";

/**
 * Three-service marketplace stack: FastAPI + Procrastinate worker + Postgres.
 *
 * Railway no longer reads railway.toml for new services (Config as Code is
 * deprecated). This file is the project-level definition. Marketplace
 * templates are still composed in the dashboard — mirror these start
 * commands, healthchecks, and private DATABASE_URL refs there.
 *
 * Postgres stays private. Do not attach a volume to API or Worker.
 * The managed postgres() helper owns its own volume.
 */
export default defineRailway(() => {
  const db = postgres("Postgres");

  const databaseUrl = db.env.DATABASE_URL;
  const python = {
    RAILPACK_PYTHON_VERSION: "3.12",
    DATABASE_URL: databaseUrl,
  };

  const api = service("API", {
    start: "python -m app.main",
    preDeploy: "python -m app.migrate",
    healthcheck: "/healthz",
    healthcheckTimeout: 100,
    env: python,
  });

  const worker = service("Worker", {
    start: "python -m app.worker",
    healthcheck: "/healthz",
    healthcheckTimeout: 120,
    env: python,
  });

  return project("fastapi-procrastinate", {
    resources: [group("Backend", [api, worker, db])],
  });
});
