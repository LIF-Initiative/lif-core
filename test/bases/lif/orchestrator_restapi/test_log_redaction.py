"""
The Orchestrator API keeps the learner identifier out of its job-request log (#1351).
"""

import logging
from unittest import mock

from httpx import ASGITransport, AsyncClient
from lif.orchestrator_restapi import core

IDENTIFIER = "SENTINEL-ID-4471"


async def test_job_request_log_has_no_learner_id(caplog):
    service = mock.Mock()
    service.submit_job = mock.AsyncMock(return_value="run-123")
    core.app.dependency_overrides[core.get_orchestrator_service] = lambda: service
    job_request = {
        "lif_query_plan": [
            {
                "information_source_id": "src1",
                "adapter_id": "lif-to-lif",
                "person_id": {"identifier": IDENTIFIER, "identifierType": "School-assigned number"},
                "lif_fragment_paths": ["Person.Name"],
            }
        ]
    }
    try:
        with caplog.at_level(logging.INFO, logger="lif.orchestrator_restapi.core"):
            async with AsyncClient(transport=ASGITransport(app=core.app), base_url="http://test") as client:
                response = await client.post("/jobs", json=job_request)
    finally:
        core.app.dependency_overrides.clear()

    assert response.status_code == 200, response.text
    assert "src1" in caplog.text
    assert IDENTIFIER not in caplog.text
