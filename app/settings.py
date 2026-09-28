from __future__ import annotations

import os
from functools import lru_cache


class Settings:
    """Runtime settings from the environment. No default admin passwords."""

    def __init__(self) -> None:
        self.database_url = (os.environ.get("DATABASE_URL") or "").strip()
        self.port = int(os.environ.get("PORT") or "43122")
        # Bind 0.0.0.0, not :: — uvicorn on :: is IPv6-only (IPV6_V6ONLY)
        # and Railway healthchecks / public edge often arrive over IPv4.
        self.host = os.environ.get("HOST") or "0.0.0.0"
        self.job_api_token = (os.environ.get("JOB_API_TOKEN") or "").strip()
        self.worker_name = os.environ.get("WORKER_NAME") or "railway-worker"
        self.worker_concurrency = int(os.environ.get("WORKER_CONCURRENCY") or "1")
        self.dns_retries = int(os.environ.get("PG_DNS_RETRIES") or "8")
        self.dns_retry_seconds = float(os.environ.get("PG_DNS_RETRY_SECONDS") or "2")
        prefer = (os.environ.get("PG_PREFER_IPV6") or "auto").strip().lower()
        self.prefer_ipv6: str = prefer
        self.log_level = (os.environ.get("LOG_LEVEL") or "INFO").upper()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
