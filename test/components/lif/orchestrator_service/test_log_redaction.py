"""
The orchestrator service keeps the learner identifier out of its job-definition log (#1351).
"""

import logging
import os
from unittest import mock

# Required at import time by the orchestrator clients, as in test_service.py.
os.environ.setdefault("LIF_ADAPTER__LIF_TO_LIF__GRAPHQL_API_URL", "http://lif-to-lif.test/graphql")

from lif.datatypes import LIFPersonIdentifier, LIFQueryPlan, LIFQueryPlanPart
from lif.orchestrator_service.service import OrchestratorService

IDENTIFIER = "SENTINEL-ID-4471"


async def test_submit_job_logs_no_learner_id(caplog, monkeypatch):
    orchestrator = mock.Mock()
    orchestrator.post_job = mock.AsyncMock(return_value="run-123")
    monkeypatch.setattr(
        "lif.orchestrator_service.service.OrchestratorFactory.create", lambda orchestrator_type, cfg: orchestrator
    )
    plan = LIFQueryPlan(
        root=[
            LIFQueryPlanPart(
                information_source_id="src1",
                adapter_id="lif-to-lif",
                person_id=LIFPersonIdentifier(identifier=IDENTIFIER, identifierType="School-assigned number"),
                lif_fragment_paths=["Person.Name"],
                translation=None,
            )
        ]
    )

    with caplog.at_level(logging.INFO, logger="lif.orchestrator_service.service"):
        await OrchestratorService(config={}).submit_job(plan)

    assert "Job definition created" in caplog.text
    assert IDENTIFIER not in caplog.text
