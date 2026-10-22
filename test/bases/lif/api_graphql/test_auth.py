"""GraphQL inbound auth: lif.auth.AuthMiddleware + api_key_strategy, off when no keys (ADR 0007)."""

from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from lif.api_graphql.core import add_api_key_auth
from lif.auth import ApiKeyConfig


def _app(config: ApiKeyConfig) -> FastAPI:
    app = FastAPI()
    add_api_key_auth(app, config)

    @app.api_route("/graphql", methods=["GET", "POST", "OPTIONS"])
    async def graphql(request: Request):
        return {"principal": getattr(request.state, "principal", None)}

    @app.get("/health")
    async def health():
        return {"ok": True}

    return app


async def _call(app, method="POST", path="/graphql", headers=None):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.request(method, path, headers=headers or {})


ENABLED = ApiKeyConfig(api_keys={"k1": "client-1"})


async def test_valid_key_sets_principal_to_client_name():
    resp = await _call(_app(ENABLED), headers={"X-API-Key": "k1"})
    assert resp.status_code == 200
    assert resp.json() == {"principal": "client-1"}


async def test_missing_and_invalid_keys_are_401_with_api_key_challenge():
    for headers in ({}, {"X-API-Key": "nope"}):
        resp = await _call(_app(ENABLED), headers=headers)
        assert resp.status_code == 401
        assert resp.headers["www-authenticate"] == "X-API-Key"


async def test_public_paths_and_options_skip_auth():
    assert (await _call(_app(ENABLED), "GET", "/health")).status_code == 200
    assert (await _call(_app(ENABLED), "OPTIONS")).status_code == 200


async def test_auth_is_off_when_no_keys_are_configured():
    assert (await _call(_app(ApiKeyConfig()))).status_code == 200
