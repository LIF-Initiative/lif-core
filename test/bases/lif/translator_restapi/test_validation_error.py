"""
The Translator API answers a bad request body with a 422 that doesn't echo the body back (#1461), in the served app and in base_test.

A non-JSON body used to give a 500, because FastAPI puts the raw bytes in each error's `input`.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from lif.translator_restapi import base_test, core

FIELD_VALUE = "SENTINEL-ID-4471"

APPS = pytest.mark.parametrize(
    ("app", "path"),
    [(core.app, "/translate/source/1/target/2"), (base_test.app, "/translate")],
    ids=["core", "base_test"],
)


def _client(app) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test")


@APPS
async def test_non_json_body_gets_422(app, path):
    async with _client(app) as client:
        response = await client.post(path, content=FIELD_VALUE, headers={"content-type": "text/plain"})

    assert response.status_code == 422
    assert FIELD_VALUE not in response.text


@APPS
async def test_422_does_not_echo_request_body(app, path):
    async with _client(app) as client:
        response = await client.post(path, json=[{"identifier": FIELD_VALUE}])

    assert response.status_code == 422
    assert set(response.json()["detail"][0]) == {"loc", "msg", "type"}
    assert FIELD_VALUE not in response.text
