"""Inbound auth for the Example Data Source (x-key header vs API_TOKEN)."""

import os

from httpx import ASGITransport, AsyncClient
from lif.example_data_source_rest_api.core import app

TOKEN = os.environ["API_TOKEN"]  # set in test/conftest.py


async def _get(path: str, headers: dict[str, str] | None = None):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.get(path, headers=headers or {})


async def test_health_is_public():
    assert (await _get("/health")).status_code == 200


async def test_docs_are_public():
    assert (await _get("/openapi.json")).status_code == 200


async def test_valid_key_is_accepted():
    assert (await _get("/users/", {"x-key": TOKEN})).status_code == 200


async def test_wrong_key_is_rejected():
    resp = await _get("/users/", {"x-key": "wrong"})
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Invalid API key."}
    assert resp.headers["www-authenticate"] == "x-key"


async def test_missing_key_is_rejected():
    # 401, not the 403 FastAPI's APIKeyHeader used to return (ADR 0007).
    resp = await _get("/users/")
    assert resp.status_code == 401
    assert resp.headers["www-authenticate"] == "x-key"


async def test_redoc_is_public():
    assert (await _get("/redoc")).status_code == 200


async def test_header_name_is_x_key_not_x_api_key():
    assert (await _get("/users/", {"X-API-Key": TOKEN})).status_code == 401


def test_missing_api_token_fails_at_startup():
    import subprocess
    import sys

    env = {k: v for k, v in os.environ.items() if k != "API_TOKEN"}
    result = subprocess.run(
        [sys.executable, "-c", "import lif.example_data_source_rest_api.core"], env=env, capture_output=True, text=True
    )
    assert result.returncode != 0
    assert "API_TOKEN is not set" in result.stderr
