import pytest
from typing import Dict, Any, cast
from enum import Enum

from lif.datatypes import (
    LIFQueryPlan,
    LIFQueryPlanPart,
    LIFPersonIdentifier,
    OrchestratorJobDefinition,
    OrchestratorJobStatus,
)
from dagster import DagsterRunStatus

import lif.orchestrator_clients.dagster as dag_mod


class DummyDagsterGraphQLClient:
    """Test double capturing constructor parameters and simulating API calls."""

    def __init__(
        self,
        hostname: str,
        port: int | None = None,
        use_https: bool | None = None,
        headers: Dict[str, str] | None = None,
    ):
        self.hostname = hostname
        self.port = port
        self.use_https = use_https
        self.headers = headers or {}
        self.submissions: list[tuple[str, Any]] = []
        self.next_run_id = "RUN-123"
        self._status_to_return: DagsterRunStatus = DagsterRunStatus.SUCCESS

    def submit_job_execution(self, job_name: str, run_config):
        self.submissions.append((job_name, run_config))
        return self.next_run_id

    def get_run_status(self, run_id: str):  # run_id ignored for test simplicity
        return self._status_to_return


def create_custom_dummy_client(
    next_run_id: str | None, status_to_return: DagsterRunStatus | None
) -> type[DummyDagsterGraphQLClient]:
    """
    Factory function to create a subclass of DummyDagsterGraphQLClient with customized attributes.
    Args:
        next_run_id (str | None): If provided, sets the `next_run_id` attribute of the client to this value.
            If None, the default value from DummyDagsterGraphQLClient is used.
        status_to_return (DagsterRunStatus | None): If provided, sets the `_status_to_return` attribute of the client to this value.
            If None, the default value from DummyDagsterGraphQLClient is used.
    Returns:
        Type[DummyDagsterGraphQLClient]: A subclass of DummyDagsterGraphQLClient with the specified attributes overridden.
    Usage:
        Use this factory to create a test double with specific run ID and status behavior for testing purposes.
    """

    class CustomDummyDagsterGraphQLClient(DummyDagsterGraphQLClient):
        def __init__(
            self,
            hostname: str,
            port: int | None = None,
            use_https: bool | None = None,
            headers: Dict[str, str] | None = None,
        ):
            super().__init__(hostname, port, use_https, headers)
            if status_to_return is not None:
                self._status_to_return = status_to_return
            if next_run_id is not None:
                self.next_run_id = next_run_id

    return CustomDummyDagsterGraphQLClient


@pytest.fixture
def plan() -> LIFQueryPlan:
    return LIFQueryPlan(
        root=[
            LIFQueryPlanPart(
                information_source_id="src1",
                adapter_id="adp1",
                person_id=LIFPersonIdentifier(identifier="p1", identifierType="test"),
                lif_fragment_paths=["person.name"],
                translation=None,
            )
        ]
    )


@pytest.fixture
def patch_client(monkeypatch):
    # Ensure env baseline (unset to allow defaults)
    for k in [
        "ORCHESTRATOR__DAGSTER__GRAPHQL_API_URL",
        "ORCHESTRATOR__DAGSTER__IS_DAGSTER_CLOUD",
        "ORCHESTRATOR__DAGSTER__GRAPHQL_API_TOKEN",
    ]:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(dag_mod, "DagsterGraphQLClient", DummyDagsterGraphQLClient)
    yield


# ---------------- Config Tests ----------------


def test_config_defaults_self_hosted():
    client = dag_mod.DagsterClient(config={})
    cfg = client._cfg  # type: ignore[attr-defined]
    assert cfg.base_url.startswith("http://")
    assert cfg.use_https is False  # default localhost http
    assert cfg.is_cloud is False


def test_config_derives_https_from_url():
    client = dag_mod.DagsterClient(config={"base_url": "https://secure-host:8443"})
    assert client._cfg.use_https is True  # type: ignore[attr-defined]


def test_cloud_requires_token(monkeypatch):
    monkeypatch.setenv("ORCHESTRATOR__DAGSTER__IS_DAGSTER_CLOUD", "True")
    monkeypatch.setenv("ORCHESTRATOR__DAGSTER__GRAPHQL_API_URL", "cloud.host")
    with pytest.raises(dag_mod.MissingEnvironmentVariableException):
        dag_mod.DagsterClient(config={})


def test_cloud_honors_token(patch_client, monkeypatch):
    monkeypatch.setenv("ORCHESTRATOR__DAGSTER__IS_DAGSTER_CLOUD", "True")
    monkeypatch.setenv("ORCHESTRATOR__DAGSTER__GRAPHQL_API_URL", "cloud.host")
    monkeypatch.setenv("ORCHESTRATOR__DAGSTER__GRAPHQL_API_TOKEN", "TKN")
    client = dag_mod.DagsterClient(config={})
    dummy = cast(DummyDagsterGraphQLClient, client._get_client())
    assert dummy.headers.get("Dagster-Cloud-Api-Token") == "TKN"


# ---------------- Client Construction ----------------


def test_self_hosted_builds_host_and_port(patch_client):
    client = dag_mod.DagsterClient(config={"base_url": "http://my-host:4000"})
    dummy = cast(DummyDagsterGraphQLClient, client._get_client())
    assert dummy.hostname == "my-host"
    assert dummy.port == 4000


# ---------------- Status Mapping ----------------
@pytest.mark.parametrize(
    "raw,expected",
    [
        (DagsterRunStatus.SUCCESS, OrchestratorJobStatus.COMPLETED),
        (DagsterRunStatus.FAILURE, OrchestratorJobStatus.FAILED),
        (DagsterRunStatus.STARTED, OrchestratorJobStatus.RUNNING),
        (DagsterRunStatus.STARTING, OrchestratorJobStatus.STARTING),
        (DagsterRunStatus.QUEUED, OrchestratorJobStatus.STARTING),
    ],
)
def test_map_status(raw, expected):
    assert dag_mod.DagsterClient._map_status(raw) == expected


def test_map_status_unmapped_raises():
    class FakeStatus(Enum):
        MYSTERY = "MYSTERY"

    with pytest.raises(dag_mod.OrchestratorStatusMappingError):
        # type: ignore[arg-type]
        dag_mod.DagsterClient._map_status(FakeStatus.MYSTERY)  # type: ignore[arg-type]


# ---------------- post_job & get_job_status ----------------
@pytest.mark.asyncio
async def test_post_job_returns_run_id(plan, monkeypatch):
    client_class = create_custom_dummy_client(next_run_id="RUN-999", status_to_return=None)
    monkeypatch.setattr(dag_mod, "DagsterGraphQLClient", client_class)
    client = dag_mod.DagsterClient(config={})
    run_id = await client.post_job(OrchestratorJobDefinition(lif_query_plan=plan))
    assert run_id == "RUN-999"


@pytest.mark.asyncio
async def test_get_job_status_maps_status(plan, monkeypatch):
    client_class = create_custom_dummy_client(next_run_id=None, status_to_return=DagsterRunStatus.FAILURE)
    monkeypatch.setattr(dag_mod, "DagsterGraphQLClient", client_class)
    client = dag_mod.DagsterClient(config={})
    job = await client.get_job_status("RUN-1")
    assert job.status == OrchestratorJobStatus.FAILED
    assert job.metadata["raw_status"] == DagsterRunStatus.FAILURE.value


@pytest.mark.asyncio
async def test_get_job_status_unmapped_raises(monkeypatch):
    class FakeStatus(Enum):
        MYSTERY = "MYSTERY"

    client_class: type[DummyDagsterGraphQLClient] = create_custom_dummy_client(
        next_run_id=None,
        status_to_return=FakeStatus.MYSTERY,  # type: ignore[arg-type]
    )
    monkeypatch.setattr(dag_mod, "DagsterGraphQLClient", client_class)
    client = dag_mod.DagsterClient(config={})
    with pytest.raises(dag_mod.OrchestratorStatusMappingError):
        await client.get_job_status("RUN-X")
