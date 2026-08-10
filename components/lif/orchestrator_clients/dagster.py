import os
import asyncio
from typing import Dict, Any, Optional
from urllib.parse import urlparse

import dagster as dg
from dagster import DagsterRunStatus
from dagster_graphql import DagsterGraphQLClient, DagsterGraphQLClientError
from pydantic import BaseModel, Field, model_validator

from lif.datatypes import OrchestratorJobDefinition, OrchestratorJob, OrchestratorJobStatus
from lif.exceptions.core import MissingEnvironmentVariableException, OrchestratorStatusMappingError
from lif.logging import get_logger
from lif.orchestrator_service.core import OrchestratorClient

logger = get_logger(__name__)

DAGSTER_JOB_NAME = "lif_dynamic_pipeline_job"


class DagsterConfig(BaseModel):
    base_url: str = Field(
        default_factory=lambda: os.getenv("ORCHESTRATOR__DAGSTER__GRAPHQL_API_URL", "http://localhost:3000")
    )
    is_cloud: bool = Field(
        default_factory=lambda: os.getenv("ORCHESTRATOR__DAGSTER__IS_DAGSTER_CLOUD", "False").lower() == "true"
    )
    api_token: Optional[str] = Field(default_factory=lambda: os.getenv("ORCHESTRATOR__DAGSTER__GRAPHQL_API_TOKEN"))
    use_https: Optional[bool] = None  # auto‑derived if not provided

    @model_validator(mode="after")
    def validate_fields(self):
        if not self.base_url:
            raise MissingEnvironmentVariableException("ORCHESTRATOR__DAGSTER__GRAPHQL_API_URL")
        if self.is_cloud and not self.api_token:
            raise MissingEnvironmentVariableException("ORCHESTRATOR__DAGSTER__GRAPHQL_API_TOKEN")
        if self.use_https is None:
            self.use_https = self.is_cloud or self.base_url.startswith("https://")
        return self


class DagsterClient(OrchestratorClient):
    _STATUS_MAPPING = {
        DagsterRunStatus.SUCCESS: OrchestratorJobStatus.COMPLETED,
        DagsterRunStatus.FAILURE: OrchestratorJobStatus.FAILED,
        DagsterRunStatus.STARTED: OrchestratorJobStatus.RUNNING,
        DagsterRunStatus.STARTING: OrchestratorJobStatus.STARTING,
        DagsterRunStatus.QUEUED: OrchestratorJobStatus.STARTING,
    }

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        # Accept raw dict; validate + normalize via Pydantic
        self._cfg = DagsterConfig(**(config or {}))
        self._client: Optional[DagsterGraphQLClient] = None

    # ---------- Internal helpers ----------

    def _build_client(self) -> DagsterGraphQLClient:
        if self._cfg.is_cloud:
            # For cloud the library expects hostname (may already be a host or full URL)
            return DagsterGraphQLClient(
                hostname=self._cfg.base_url,
                use_https=bool(self._cfg.use_https),
                # ty-ignore: dagster-graphql stubs type `headers` more narrowly than the runtime API.
                headers={"Dagster-Cloud-Api-Token": self._cfg.api_token},  # ty: ignore[invalid-argument-type]
            )
        parsed = urlparse(self._cfg.base_url)
        host = parsed.hostname
        if not host:
            raise ValueError(f"Invalid Dagster base_url: {self._cfg.base_url}")
        port = parsed.port or (443 if self._cfg.use_https else 80)
        return DagsterGraphQLClient(host, port)

    def _get_client(self) -> DagsterGraphQLClient:
        temp_client = self._build_client()
        logger.debug("Initialized DagsterGraphQLClient (%s)", "cloud" if self._cfg.is_cloud else "self-hosted")
        return temp_client

    async def _run_blocking(self, func, *args, **kwargs):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: func(*args, **kwargs))

    @staticmethod
    def _map_status(raw: DagsterRunStatus) -> OrchestratorJobStatus:
        if raw in DagsterClient._STATUS_MAPPING:
            return DagsterClient._STATUS_MAPPING[raw]

        raise OrchestratorStatusMappingError("dagster", raw.value)

    # ---------- OrchestratorClient interface ----------

    async def post_job(self, job_definition: OrchestratorJobDefinition) -> str:
        temp_client = self._get_client()

        run_config = dg.RunConfig(
            resources={
                "config_resource": {"config": {"lif_query_plan_parts": job_definition.lif_query_plan.model_dump()}}
            }
        )

        # TODO: Change to debug level once stable
        logger.info(f"Submitting Dagster job with config: {run_config.to_config_dict()}")

        try:
            run_id: str = await self._run_blocking(
                temp_client.submit_job_execution, DAGSTER_JOB_NAME, run_config=run_config
            )
            logger.info("Dagster run submitted: %s", run_id)
            return run_id
        except DagsterGraphQLClientError:
            logger.exception("Dagster submission failed")
            raise

    async def get_job_status(self, job_id: str) -> OrchestratorJob:
        client = self._get_client()
        try:
            raw_status: DagsterRunStatus = await self._run_blocking(client.get_run_status, job_id)
        except DagsterGraphQLClientError as exc:
            logger.error("Dagster status fetch failed for %s: %s", job_id, exc)
            raise

        mapped = self._map_status(raw_status)
        return OrchestratorJob(job_id=job_id, status=mapped, metadata={"raw_status": raw_status.value})

    # ---------- Optional lifecycle ----------

    async def close(self):
        # Placeholder for future resource cleanup
        self._client = None
