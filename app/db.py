"""IPv6-safe Postgres connect helper for Railway private networking.

Station pitfall
---------------
``*.railway.internal`` is IPv6-first (legacy environments are IPv6-only;
environments created after 16 Oct 2025 are dual-stack). Python clients that
resolve IPv4 first — especially **asyncpg** and SQLAlchemy's asyncpg dialect —
connect to a dead A record, hang until timeout, then never try the AAAA
record. Symptom: ``Connect call failed`` / ``TimeoutError`` against
``postgres.railway.internal`` while ``psql`` or Node works.

This helper:

1. Parses ``DATABASE_URL`` (postgres / postgresql / +asyncpg / +psycopg).
2. Resolves the host with ``AF_UNSPEC`` and **prefers IPv6** for
   ``*.railway.internal`` (dual-stack elsewhere, still IPv6-first by default).
3. Returns **kwargs** (host as a bare IP). Pass those to asyncpg / SQLAlchemy
   ``connect_args`` / psycopg. Do **not** put a raw IPv6 literal back into a
   URI — asyncpg has historically mis-parsed ``[v6]:port``.
4. Disables SSL on the private mesh (no TLS there); honors ``sslmode`` and
   enables SSL for public Railway TCP proxies (``*.rlwy.net``).
5. Retries DNS — private nameservers can be empty for a few seconds after boot.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
import time
from dataclasses import dataclass, field
from typing import Any, Literal
from urllib.parse import parse_qs, unquote, urlparse

from app.settings import get_settings

log = logging.getLogger(__name__)

RAILWAY_INTERNAL_SUFFIX = ".railway.internal"
_DIALECT_PREFIXES = (
    "postgresql+asyncpg://",
    "postgresql+psycopg://",
    "postgresql+psycopg2://",
    "postgres+asyncpg://",
    "postgres+psycopg://",
)


@dataclass(frozen=True)
class DatabaseTarget:
    user: str
    password: str
    host: str
    port: int
    database: str
    sslmode: str
    query: dict[str, list[str]] = field(default_factory=dict)
    original_host: str = ""
    family: int | None = None

    @property
    def is_ipv6(self) -> bool:
        try:
            return isinstance(ipaddress.ip_address(self.host), ipaddress.IPv6Address)
        except ValueError:
            return False


def normalize_database_url(raw: str) -> str:
    url = raw.strip()
    for prefix in _DIALECT_PREFIXES:
        if url.startswith(prefix):
            return "postgresql://" + url.split("://", 1)[1]
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://") :]
    return url


def parse_database_url(raw: str) -> DatabaseTarget:
    url = normalize_database_url(raw)
    parsed = urlparse(url)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise ValueError(f"Unsupported DATABASE_URL scheme: {parsed.scheme!r}")
    host = parsed.hostname
    if not host:
        raise ValueError("DATABASE_URL is missing a hostname")
    port = parsed.port or 5432
    user = unquote(parsed.username or "postgres")
    password = unquote(parsed.password or "")
    database = unquote(parsed.path.lstrip("/") or "postgres")
    query = parse_qs(parsed.query)
    sslmode = (query.get("sslmode") or [""])[0].lower()
    if not sslmode:
        sslmode = infer_sslmode(host)
    return DatabaseTarget(
        user=user,
        password=password,
        host=host,
        port=port,
        database=database,
        sslmode=sslmode,
        query=query,
        original_host=host,
    )


def infer_sslmode(host: str) -> str:
    lowered = host.lower()
    if lowered.endswith(RAILWAY_INTERNAL_SUFFIX):
        return "disable"
    if lowered.endswith(".rlwy.net") or lowered.endswith(".railway.app"):
        return "require"
    try:
        addr = ipaddress.ip_address(host)
        if addr.is_private or addr.is_loopback or addr.is_link_local:
            return "disable"
    except ValueError:
        pass
    return "prefer"


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def should_prefer_ipv6(host: str, preference: str = "auto") -> bool:
    if preference in {"1", "true", "yes", "ipv6"}:
        return True
    if preference in {"0", "false", "no", "ipv4"}:
        return False
    return host.lower().endswith(RAILWAY_INTERNAL_SUFFIX) or preference == "auto"


def resolve_host(
    host: str,
    *,
    prefer_ipv6: bool = True,
    retries: int = 8,
    retry_seconds: float = 2.0,
) -> tuple[str, int]:
    """Return ``(ip, address_family)``. Retries DNS for Railway boot races."""
    if _is_ip(host):
        family = (
            socket.AF_INET6
            if isinstance(ipaddress.ip_address(host), ipaddress.IPv6Address)
            else socket.AF_INET
        )
        return host, family

    last_error: OSError | None = None
    attempts = max(1, retries)
    for attempt in range(1, attempts + 1):
        try:
            infos = socket.getaddrinfo(host, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        except OSError as exc:
            last_error = exc
            log.warning(
                "DNS lookup failed for %s (%s/%s): %s",
                host,
                attempt,
                attempts,
                exc,
            )
            if attempt < attempts:
                time.sleep(retry_seconds)
            continue

        candidates: list[tuple[int, str]] = []
        for family, _type, _proto, _canon, sockaddr in infos:
            if family not in {socket.AF_INET, socket.AF_INET6}:
                continue
            candidates.append((family, sockaddr[0]))
        if not candidates:
            last_error = OSError(f"no A/AAAA records for {host}")
            if attempt < attempts:
                time.sleep(retry_seconds)
            continue

        def _sort_key(item: tuple[int, str]) -> tuple[int, str]:
            family, addr = item
            ipv6_first = 0 if family == socket.AF_INET6 else 1
            ipv4_first = 0 if family == socket.AF_INET else 1
            return (ipv6_first if prefer_ipv6 else ipv4_first, addr)

        family, addr = sorted(candidates, key=_sort_key)[0]
        log.info(
            "Resolved %s -> %s (%s, prefer_ipv6=%s)",
            host,
            addr,
            "IPv6" if family == socket.AF_INET6 else "IPv4",
            prefer_ipv6,
        )
        return addr, family

    raise ConnectionError(
        f"Could not resolve {host!r} after {attempts} attempt(s): {last_error}"
    )


def resolve_target(raw_url: str | None = None) -> DatabaseTarget:
    settings = get_settings()
    url = (raw_url or settings.database_url).strip()
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. On Railway, reference the private URL: "
            "${{Postgres.DATABASE_URL}} or "
            "postgresql://${{Postgres.PGUSER}}:${{Postgres.PGPASSWORD}}"
            "@${{Postgres.RAILWAY_PRIVATE_DOMAIN}}:5432/${{Postgres.PGDATABASE}}"
        )
    parsed = parse_database_url(url)
    prefer = should_prefer_ipv6(parsed.host, settings.prefer_ipv6)
    host, family = resolve_host(
        parsed.host,
        prefer_ipv6=prefer,
        retries=settings.dns_retries,
        retry_seconds=settings.dns_retry_seconds,
    )
    return DatabaseTarget(
        user=parsed.user,
        password=parsed.password,
        host=host,
        port=parsed.port,
        database=parsed.database,
        sslmode=parsed.sslmode,
        query=parsed.query,
        original_host=parsed.original_host,
        family=family,
    )


def asyncpg_kwargs(target: DatabaseTarget | None = None) -> dict[str, Any]:
    """Keyword args for ``asyncpg.connect`` / SQLAlchemy ``connect_args``."""
    t = target or resolve_target()
    ssl: bool | Literal["prefer"]
    if t.sslmode in {"disable", "allow"}:
        ssl = False
    elif t.sslmode in {"require", "verify-ca", "verify-full"}:
        ssl = True
    else:
        ssl = "prefer"
    return {
        "host": t.host,
        "port": t.port,
        "user": t.user,
        "password": t.password,
        "database": t.database,
        "ssl": ssl,
    }


def psycopg_kwargs(target: DatabaseTarget | None = None) -> dict[str, Any]:
    """Keyword args for ``psycopg`` / Procrastinate ``PsycopgConnector``."""
    t = target or resolve_target()
    return {
        "host": t.host,
        "port": t.port,
        "user": t.user,
        "password": t.password,
        "dbname": t.database,
        "sslmode": t.sslmode,
    }


def sqlalchemy_async_url() -> str:
    """Dialect-only URL. Pass host via ``connect_args=asyncpg_kwargs()``."""
    return "postgresql+asyncpg://"


def sqlalchemy_sync_url() -> str:
    return "postgresql+psycopg://"
