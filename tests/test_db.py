from __future__ import annotations

import socket

import pytest

from app.db import (
    infer_sslmode,
    parse_database_url,
    resolve_host,
    should_prefer_ipv6,
)


def test_parse_private_railway_url() -> None:
    target = parse_database_url(
        "postgresql://user:p%40ss@postgres.railway.internal:5432/railway"
    )
    assert target.host == "postgres.railway.internal"
    assert target.port == 5432
    assert target.user == "user"
    assert target.password == "p@ss"
    assert target.database == "railway"
    assert target.sslmode == "disable"


def test_parse_asyncpg_dialect_and_public_ssl() -> None:
    target = parse_database_url(
        "postgresql+asyncpg://postgres:x@shortline.proxy.rlwy.net:12345/railway"
    )
    assert target.host == "shortline.proxy.rlwy.net"
    assert target.sslmode == "require"


def test_infer_sslmode() -> None:
    assert infer_sslmode("postgres.railway.internal") == "disable"
    assert infer_sslmode("127.0.0.1") == "disable"
    assert infer_sslmode("shortline.proxy.rlwy.net") == "require"


def test_prefer_ipv6_for_private_dns() -> None:
    assert should_prefer_ipv6("postgres.railway.internal", "auto") is True
    assert should_prefer_ipv6("db.example.com", "auto") is True
    assert should_prefer_ipv6("db.example.com", "ipv4") is False
    assert should_prefer_ipv6("postgres.railway.internal", "ipv4") is False


def test_resolve_host_prefers_aaaa(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_getaddrinfo(host, _port, family, _type):
        assert host == "postgres.railway.internal"
        assert family == socket.AF_UNSPEC
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 5432)),
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("fd12::10", 5432, 0, 0)),
        ]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    ip, family = resolve_host(
        "postgres.railway.internal", prefer_ipv6=True, retries=1, retry_seconds=0
    )
    assert ip == "fd12::10"
    assert family == socket.AF_INET6


def test_resolve_host_can_prefer_ipv4(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_getaddrinfo(host, _port, family, _type):
        return [
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("fd12::10", 5432, 0, 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 5432)),
        ]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    ip, family = resolve_host("db.example.com", prefer_ipv6=False, retries=1)
    assert ip == "10.0.0.5"
    assert family == socket.AF_INET


def test_resolve_host_retries_empty_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def fake_getaddrinfo(host, _port, family, _type):
        calls["n"] += 1
        if calls["n"] < 3:
            raise socket.gaierror(-2, "Name or service not known")
        return [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("fd12::aa", 0, 0, 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    ip, family = resolve_host("postgres.railway.internal", retries=5, retry_seconds=0)
    assert ip == "fd12::aa"
    assert family == socket.AF_INET6
    assert calls["n"] == 3
