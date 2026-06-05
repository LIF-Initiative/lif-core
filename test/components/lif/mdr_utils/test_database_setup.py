"""Unit tests for `database_setup` — `_redact_url` (#938) and the per-request
`get_session` search_path routing (#961, tenant isolation).

The full `database_setup` module imports SQLAlchemy/asyncpg/etc at import
time and tries to construct an engine from env vars; the sibling `conftest.py`
seeds dummy env so the import (and engine construction) succeeds without a DB.
The `get_session` tests patch `async_session`, so no real connection is made."""

# cspell:ignore mydb dbhost cret unparseable agen sw0rd

import types
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from lif.mdr_utils import database_setup
from lif.mdr_utils.database_setup import _redact_url, get_session


class TestRedactUrl:
    def test_masks_password_in_typical_postgres_url(self):
        url = "postgresql+asyncpg://postgres:s3cret!@dbhost.example:5432/mydb"
        assert _redact_url(url) == "postgresql+asyncpg://postgres:***@dbhost.example:5432/mydb"

    def test_masks_password_with_special_characters(self):
        # Real dev password observed in CloudWatch had `:`, `}`, `&`, `<`, `$`
        # in it. urlparse handles percent-encoding; here we use a
        # representative literal to confirm the redaction doesn't choke.
        url = "postgresql+asyncpg://postgres:p:%24sw0rd@host:5432/db"
        redacted = _redact_url(url)
        assert "p:%24sw0rd" not in redacted
        assert "postgres:***@host:5432/db" in redacted

    def test_url_without_port_still_redacts(self):
        url = "postgresql+asyncpg://postgres:s3cret@host/db"
        # No explicit port — netloc is just user:pass@host. Redacted form
        # must drop the password but keep everything else.
        redacted = _redact_url(url)
        assert "s3cret" not in redacted
        assert "postgres:***@host" in redacted
        assert "/db" in redacted

    def test_url_without_password_is_unchanged(self):
        # IAM-auth style (no password), or local trust auth — we return
        # the original string rather than mangling it.
        url = "postgresql+asyncpg://postgres@host:5432/db"
        assert _redact_url(url) == url

    def test_unparseable_input_does_not_raise(self):
        # The function is only ever called for logging; if it raises,
        # MDR startup fails. Return a sentinel string instead so the
        # log line still emits something operator-readable.
        # urlparse is famously tolerant — `urlparse("")` returns an
        # empty ParseResult rather than raising — so this test really
        # documents the "no exception" guarantee.
        assert _redact_url("") == ""
        assert _redact_url("not-a-url") == "not-a-url"


def _make_request(tenant_schema):
    """Minimal stand-in for the FastAPI Request `get_session` reads."""
    return types.SimpleNamespace(state=types.SimpleNamespace(tenant_schema=tenant_schema))


def _patch_session(monkeypatch, schema_exists=True):
    """Patch `async_session` so `get_session` runs without a real DB.

    `schema_exists` controls what the `information_schema.schemata` existence
    probe returns (`.first()` → a row when True, else None). Returns the mock
    session whose `.execute` records the SQL it was handed.
    """
    session = AsyncMock()
    result = MagicMock()
    result.first.return_value = (1,) if schema_exists else None
    session.execute.return_value = result
    ctx = AsyncMock()
    ctx.__aenter__.return_value = session
    ctx.__aexit__.return_value = False
    monkeypatch.setattr(database_setup, "async_session", MagicMock(return_value=ctx))
    return session


def _executed_sql(session):
    return [str(call.args[0]) for call in session.execute.call_args_list]


async def _drive(request):
    """Run `get_session` like a FastAPI dependency: enter, yield, close."""
    agen = get_session(request)
    await agen.__anext__()
    await agen.aclose()


class TestGetSessionSearchPath:
    """#961 — the per-request `SET search_path` is the *entire* tenant-isolation
    boundary, so lock its behavior: route tenant-first, fail closed on anything
    the sanitizer wouldn't emit, and always reset (pooled connections persist
    search_path across requests)."""

    async def test_valid_existing_tenant_routes_tenant_first_then_public(self, monkeypatch):
        session = _patch_session(monkeypatch, schema_exists=True)
        await _drive(_make_request("tenant_acme"))
        sql = _executed_sql(session)
        # Existence is verified first, then routed tenant-first (public last so
        # PG-level types still resolve).
        assert any("information_schema.schemata" in s for s in sql)
        assert sql[-1] == 'SET search_path TO "tenant_acme", public'

    async def test_resolved_but_missing_schema_fails_closed(self, monkeypatch):
        # #961 part 2: a valid-format schema that isn't provisioned must DENY,
        # not silently fall through to `public`. The existence probe runs, but
        # search_path is never pointed at the missing schema.
        session = _patch_session(monkeypatch, schema_exists=False)
        agen = get_session(_make_request("tenant_ghost"))
        with pytest.raises(HTTPException) as exc_info:
            await agen.__anext__()
        assert exc_info.value.status_code == 500
        assert not any("SET search_path" in s for s in _executed_sql(session))

    async def test_no_tenant_resets_to_public(self, monkeypatch):
        # A non-tenant request MUST still issue a SET — otherwise a pooled
        # connection last used for tenant A would leak A's schema into this
        # request. This is the cross-tenant-leak regression guard.
        session = _patch_session(monkeypatch)
        await _drive(_make_request(None))
        assert _executed_sql(session) == ["SET search_path TO public"]

    @pytest.mark.parametrize(
        "malicious",
        [
            'tenant_a"; DROP SCHEMA public CASCADE; --',  # injection via the schema name
            'public", "tenant_b',  # smuggle a second schema into the SET
            "tenant_a, tenant_b",  # comma — widen search_path to another tenant
            "tenant a",  # space
            "1tenant",  # leading digit (pattern requires letter/underscore first)
            "a" * 64,  # 64 chars — exceeds the 63-char identifier cap
            "tenant_a'; SELECT 1",  # quote-based injection
        ],
    )
    async def test_malformed_or_injection_schema_fails_closed(self, monkeypatch, malicious):
        # A tenant_schema the sanitizer would never emit means a resolver bug or
        # a tampered value — fail the request (500) rather than route it, and
        # crucially do so BEFORE any SET runs so no injected SQL executes.
        session = _patch_session(monkeypatch)
        agen = get_session(_make_request(malicious))
        with pytest.raises(HTTPException) as exc_info:
            await agen.__anext__()
        assert exc_info.value.status_code == 500
        assert session.execute.await_count == 0
