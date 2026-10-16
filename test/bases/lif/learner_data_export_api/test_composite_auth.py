"""LDE inbound auth: lif.auth.AuthMiddleware in both modes (ADR 0007, #1034)."""

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from lif.auth import ApiKeyConfig
from lif.auth.cognito import CognitoAuthConfig
from lif.learner_data_export_api.core import add_inbound_auth

COGNITO = CognitoAuthConfig(user_pool_id="us-east-1_TestPool", client_id="client")


def _app(mode: str, api_key_config: ApiKeyConfig, cognito_config: CognitoAuthConfig = COGNITO) -> FastAPI:
    app = FastAPI()
    add_inbound_auth(app, mode, api_key_config, cognito_config)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/ready")
    async def ready():
        return {"status": "ok"}

    @app.get("/protected")
    async def protected(request: Request):
        return {
            "principal": getattr(request.state, "principal", None),
            "auth_method": getattr(request.state, "auth_method", None),
        }

    return app


async def _get(app: FastAPI, path: str = "/protected", headers: dict[str, str] | None = None):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.get(path, headers=headers or {})


# ---- api_key mode (the default) ----


async def test_api_key_mode_accepts_a_known_key():
    resp = await _get(_app("api_key", ApiKeyConfig(api_keys={"k1": "client-1"})), headers={"X-API-Key": "k1"})
    assert resp.status_code == 200
    assert resp.json() == {"principal": "client-1", "auth_method": "api_key"}


async def test_api_key_mode_rejects_missing_or_unknown_keys():
    app = _app("api_key", ApiKeyConfig(api_keys={"k1": "client-1"}))
    assert (await _get(app)).status_code == 401
    assert (await _get(app, headers={"X-API-Key": "nope"})).status_code == 401
    assert (await _get(app, "/health")).status_code == 200


async def test_api_key_mode_is_open_without_keys():
    assert (await _get(_app("api_key", ApiKeyConfig()))).status_code == 200


# ---- composite mode (what AWS runs): developer-key stub, then Cognito ----


@pytest.fixture
def cognito_accepts(monkeypatch):
    import lif.auth.cognito as cognito

    monkeypatch.setattr(cognito, "decode_cognito_jwt", lambda token, config: {"sub": f"sub-{token}"})


async def test_composite_mode_authenticates_cognito_bearer(cognito_accepts):
    resp = await _get(_app("composite", ApiKeyConfig()), headers={"Authorization": "Bearer abc"})
    assert resp.status_code == 200
    assert resp.json() == {"principal": "sub-abc", "auth_method": "cognito"}


async def test_composite_mode_rejects_without_credentials():
    resp = await _get(_app("composite", ApiKeyConfig()))
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Missing or invalid credentials"}


async def test_composite_mode_honours_configured_public_paths():
    # LDE_AUTH__PUBLIC_PATHS* were ignored in composite mode before ADR 0007.
    app = _app("composite", ApiKeyConfig(public_paths={"/ready"}, public_path_prefixes=set()))
    assert (await _get(app, "/ready")).status_code == 200
    assert (await _get(app, "/health")).status_code == 401
