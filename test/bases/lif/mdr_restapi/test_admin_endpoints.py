"""Endpoint tests for GET /admin/schema-state (#1226).

Minimal app with AuthMiddleware and the admin router; the drift service is mocked
so these run without Postgres. The SQL those functions issue is Postgres-specific
(information_schema) and is exercised against a real database, not here.
"""

# database_setup builds a SQLAlchemy engine at import time from POSTGRESQL_*.
# These tests override the session dependency and never touch the engine, but
# the URL still has to parse.
import os

os.environ.setdefault("POSTGRESQL_USER", "test")
os.environ.setdefault("POSTGRESQL_PASSWORD", "test")
os.environ.setdefault("POSTGRESQL_HOST", "localhost")
os.environ.setdefault("POSTGRESQL_PORT", "5432")
os.environ.setdefault("POSTGRESQL_DB", "test")

from unittest import mock  # noqa: E402

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from lif.mdr_auth.core import AuthMiddleware  # noqa: E402
from lif.mdr_restapi import admin_endpoints  # noqa: E402

pytestmark = pytest.mark.asyncio

VALID_SERVICE_KEY = "changeme1"  # matches settings.mdr__auth__service_api_key__graphql default

APPLIED = [
    {"version": "1.6", "description": "attributes target entity id", "success": True, "installed_on": "2026-09-14"},
    {"version": "1.5", "description": "developer api keys", "success": True, "installed_on": "2026-08-05"},
]


def _build_app(applied, schemas) -> FastAPI:
    app = FastAPI()
    app.add_middleware(AuthMiddleware)

    async def fake_session():
        yield mock.MagicMock()

    app.dependency_overrides[admin_endpoints.get_session] = fake_session
    app.include_router(admin_endpoints.router, prefix="/admin")
    return app


async def _get(app, headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.get("/admin/schema-state", headers=headers)


async def test_reports_drifted_schemas_even_when_flyway_says_success(monkeypatch):
    """#1226/#1265: the whole point — Flyway green while tenant schemas are behind.

    This is the exact state of dev on 2026-09-17: flyway_schema_history read 1.6
    Success while 9 schemas were missing the column 1.6 added. A check that read
    only the migration history would have reported healthy.
    """
    schemas = [
        {"schema": "tenant_lif_team", "missing": ["Attributes.TargetEntityId"]},
        {"schema": "tenant_eval_abc", "missing": ["Attributes.TargetEntityId"]},
    ]
    monkeypatch.setattr(
        admin_endpoints.schema_drift_service, "applied_migrations", mock.AsyncMock(return_value=APPLIED)
    )
    monkeypatch.setattr(
        admin_endpoints.schema_drift_service, "tenant_schema_drift", mock.AsyncMock(return_value=schemas)
    )

    response = await _get(_build_app(APPLIED, schemas), {"X-API-Key": VALID_SERVICE_KEY})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["latest_version"] == "1.6"
    assert body["drifted_schema_count"] == 2
    assert {s["schema_name"] for s in body["schemas"]} == {"tenant_lif_team", "tenant_eval_abc"}
    assert body["schemas"][0]["missing"] == ["Attributes.TargetEntityId"]


async def test_clean_database_reports_no_drift(monkeypatch):
    schemas = [{"schema": "tenant_lif_team", "missing": []}]
    monkeypatch.setattr(
        admin_endpoints.schema_drift_service, "applied_migrations", mock.AsyncMock(return_value=APPLIED)
    )
    monkeypatch.setattr(
        admin_endpoints.schema_drift_service, "tenant_schema_drift", mock.AsyncMock(return_value=schemas)
    )

    response = await _get(_build_app(APPLIED, schemas), {"X-API-Key": VALID_SERVICE_KEY})

    assert response.status_code == 200
    assert response.json()["drifted_schema_count"] == 0


async def test_empty_history_means_flyway_never_ran(monkeypatch):
    """No flyway_schema_history is an answer, not an error."""
    monkeypatch.setattr(admin_endpoints.schema_drift_service, "applied_migrations", mock.AsyncMock(return_value=[]))
    monkeypatch.setattr(admin_endpoints.schema_drift_service, "tenant_schema_drift", mock.AsyncMock(return_value=[]))

    response = await _get(_build_app([], []), {"X-API-Key": VALID_SERVICE_KEY})

    assert response.status_code == 200
    assert response.json()["latest_version"] is None
    assert response.json()["applied_migrations"] == []


async def test_unauthenticated_caller_is_rejected_by_the_middleware():
    """No credentials at all never reaches the route -- AuthMiddleware stops it first."""
    response = await _get(_build_app(APPLIED, []), {})
    assert response.status_code == 401, response.text


async def test_a_cognito_user_is_rejected_by_the_dependency(monkeypatch):
    """The check that actually matters: authenticated, but not a service principal.

    The previous version of this test sent no headers and asserted `in (401, 403)`.
    That passes on the middleware's 401 without ever reaching
    `require_service_principal`, so it proved nothing about the dependency. A loose
    assertion was hiding the fact that I did not know which code path ran.
    """
    monkeypatch.setattr(
        admin_endpoints.schema_drift_service, "applied_migrations", mock.AsyncMock(return_value=APPLIED)
    )
    monkeypatch.setattr(admin_endpoints.schema_drift_service, "tenant_schema_drift", mock.AsyncMock(return_value=[]))

    app = FastAPI()  # no AuthMiddleware: exercise the dependency in isolation

    async def fake_session():
        yield mock.MagicMock()

    app.dependency_overrides[admin_endpoints.get_session] = fake_session
    app.include_router(admin_endpoints.router, prefix="/admin")

    @app.middleware("http")
    async def as_cognito_user(request, call_next):
        request.state.principal = "user:alice@example.com"  # authenticated, not a service
        return await call_next(request)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/admin/schema-state")

    assert response.status_code == 403, response.text
    assert response.json()["detail"] == "Service principal required"
