"""
The Example Data Source API keeps user identifiers and search values out of its request logs (#1351).
"""

import logging
import os

import pytest
from httpx import ASGITransport, AsyncClient
from lif.example_data_source_rest_api import core

API_TOKEN = os.environ["API_TOKEN"]  # set in test/conftest.py; core reads it at import
IDENTIFIER = "SENTINEL-ID-4471"
NUMERIC_IDENTIFIER = "447144714"


@pytest.mark.parametrize(
    ("path", "params", "sentinel", "logged"),
    [
        (f"/r1-demo/users/{IDENTIFIER}", {}, IDENTIFIER, "r1_demo_get_user endpoint was called"),
        (f"/users/{NUMERIC_IDENTIFIER}", {}, NUMERIC_IDENTIFIER, "get_user endpoint was called"),
        ("/students/", {"name": IDENTIFIER, "name_like": IDENTIFIER}, IDENTIFIER, "Filter keys"),
    ],
)
async def test_request_log_has_no_learner_value(caplog, path, params, sentinel, logged):
    with caplog.at_level(logging.INFO, logger="lif.example_data_source_rest_api.core"):
        async with AsyncClient(transport=ASGITransport(app=core.app), base_url="http://test") as client:
            response = await client.get(path, params=params, headers={"x-key": API_TOKEN})

    assert response.status_code in (200, 404), response.text
    assert logged in caplog.text
    assert sentinel not in caplog.text
