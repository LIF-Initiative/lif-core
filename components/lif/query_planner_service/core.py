"""
LIF Query Planner Service (Async Version).

This component provides a service that accepts LIF queries
and returns query results.
"""

from datetime import datetime, timezone
from typing import Dict, List

import httpx
from pydantic import BaseModel, Field

from lif.datatypes import (
    OrchestratorJobRequest,
    OrchestratorJobRequestResponse,
    OrchestratorJobResults,
    LIFFragment,
    LIFQuery,
    LIFQueryFilter,
    LIFQueryPlan,
    LIFQueryStatusResponse,
    LIFPersonIdentifier,
    LIFRecord,
    LIFUpdate,
)
from lif.exceptions.core import LIFException
from lif.logging.core import get_logger
from lif.query_planner_service.datatypes import LIFQueryPlannerConfig
from lif.query_planner_service import util

logger = get_logger(__name__)

JOB_EXPIRY_HOURS: int = 1
JOB_MAX_CACHE_SIZE: int = 200


class LIFQueryPlannerService:
    """
    LIF Query Planner Service class.

    Attributes:
        config (LIFQueryPlannerConfig): Configuration for the service.
    """

    def __init__(self, config: LIFQueryPlannerConfig):
        self.config = config
        self.information_sources_config = self.config.information_sources_config
        self.lif_cache_url = config.lif_cache_url.rstrip("/")
        self.lif_orchestrator_url = config.lif_orchestrator_url.rstrip("/")
        self.lif_cache_query_url = self.lif_cache_url + "/query"
        self.lif_cache_update_url = self.lif_cache_url + "/update"
        self.lif_cache_save_url = self.lif_cache_url + "/save"
        self.lif_orchestrator_post_url = self.lif_orchestrator_url + "/jobs"

    # Main function to run a query
    # -------------------------------------------------------------------------
    async def run_query(self, query: LIFQuery, first_run: bool) -> List[LIFRecord] | LIFQueryStatusResponse:
        """
        Execute a LIF query.

        Args:
            query (LIFQuery): Input query with filter and selected fields.

        Returns:
            List[LIFRecord]: List of matching LIF records (persons) from the database, with only
                       requested fields present.

        Raises:
            LIFException: If the query fails.
        """
        try:
            # Send the query to the LIF Cache service
            lif_records: List[LIFRecord] = await query_lif_cache(self.lif_cache_query_url, query)

            # Raise an error if multiple records are found
            if len(lif_records) > 1:
                raise LIFException("Multiple records found for the query, expected only one.")

            # Get the LIF fragment paths from the query
            lif_fragment_paths: List[str] = util.get_lif_fragment_paths_from_query(query)

            # If the LIF Record contains all the fields requested, we can return it directly
            lif_fragment_paths_not_found: List[str] = (
                util.get_lif_fragment_paths_not_found_in_lif_record(lif_records[0], lif_fragment_paths)
                if lif_records
                else lif_fragment_paths
            )

            if not lif_fragment_paths_not_found:
                logger.info("LIF Record contains all requested fields, returning directly.")
                return lif_records
            logger.info(f"LIF Record does not contain all requested fields, missing: {lif_fragment_paths_not_found}")

            if first_run:
                # Otherwise create a query plan, call the Orchestrator, and return a Query ID
                lif_person_identifier: LIFPersonIdentifier = query.filter.root.person.identifier[0]
                # Note: Used to send lif_fragment_paths_not_found to create the query plan, but this prevented
                # having the ability to query Org3 if there were already records from Org1 with the same schema
                # so now lif_fragment_paths is sent to always get all fields
                lif_query_plan: LIFQueryPlan = util.create_lif_query_plan_from_information_sources_config(
                    lif_person_identifier, self.information_sources_config, lif_fragment_paths
                )
                logger.info(f"Created LIF Query Plan: {lif_query_plan}")

                if not lif_query_plan.root:
                    logger.warning(
                        f"No information sources found for the requested LIF fragment paths: {lif_fragment_paths}. Returning LIF records found in cache."
                    )
                    return lif_records

                orchestrator_job_request: OrchestratorJobRequest = OrchestratorJobRequest(
                    lif_query_plan=lif_query_plan,
                    async_=True,  # ty: ignore[unknown-argument]
                )

                try:
                    orchestrator_job_request_response: OrchestratorJobRequestResponse = await post_orchestrator_job(
                        self.lif_orchestrator_post_url, orchestrator_job_request
                    )
                except Exception as e:
                    logger.error(f"Returning LIF records found so far: {lif_records}")
                    return lif_records

                lif_query_planner_job = LIFQueryPlannerJob(
                    job_id=orchestrator_job_request_response.run_id, query=query, status="PENDING"
                )

                # prune_job_store()

                # Store the job in the JOB_STORE
                JOB_STORE[lif_query_planner_job.job_id] = lif_query_planner_job
                query_status_response = LIFQueryStatusResponse(query_id=lif_query_planner_job.job_id, status="PENDING")
                return query_status_response
            else:
                logger.info("Orchestrator already called, returning LIF records found so far.")
                return lif_records
        except httpx.HTTPStatusError as e:
            raise e
        except Exception as e:
            msg = f"LIF Query Planner error: {e}"
            logger.exception(msg)
            raise LIFException(msg) from e

    # -------------------------------------------------------------------------
    # Main function to get the status of a query
    # -------------------------------------------------------------------------
    async def get_query_status(self, query_id: str) -> LIFQueryStatusResponse:
        """
        Get the status of a query by its ID.

        Args:
            query_id (str): The ID of the query.

        Returns:
            LIFQueryStatusResponse: The status of the query.

        Raises:
            ValueError: If the job ID is invalid.
            LIFException: If an error occurs while retrieving the job status.
        """
        try:
            if query_id not in JOB_STORE:
                raise ValueError(f"Invalid query ID: {query_id}")
            job: LIFQueryPlannerJob = JOB_STORE[query_id]
            if job.status == "PENDING" or job.status == "COMPLETED":
                return LIFQueryStatusResponse(query_id=query_id, status=job.status)
            else:
                raise LIFException(f"Query with ID {query_id} is in an unknown state: {job.status}")
        except ValueError as e:
            raise e
        except Exception as e:
            logger.exception(f"Error retrieving query status: {e}")
            raise LIFException(f"Error retrieving query status: {e}") from e

    # Main function to run an update
    # -------------------------------------------------------------------------
    async def run_update(self, update: LIFUpdate) -> LIFRecord:
        """
        Execute a LIF update on the LIF Cache.

        Args:
            input (LIFUpdate): Input model containing filter and update fields.

        Returns:
            LIFRecord: The LIFRecord for the updated 'person' array (without '_id').

        Raises:
            LIFException: If the update fails.
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(self.lif_cache_update_url, json=update.model_dump())
            response.raise_for_status()
            response_json = response.json()
            return response_json
        except httpx.HTTPStatusError as e:
            raise e
        except Exception as e:
            msg = f"LIF Query Planner error: {e}"
            logger.exception(msg)
            raise LIFException(msg) from e

    # -------------------------------------------------------------------------
    # Main function to post orchestration results
    # -------------------------------------------------------------------------
    async def run_post_orchestration_results(self, results: OrchestratorJobResults) -> None:
        """
        Post orchestration job results.

        Args:
            results (OrchestratorJobResults): Orchestration job results to post.

        Returns:
            None

        Raises:
            LIFException: If posting results fails.
        """
        logger.info(f"Received orchestration results for Run ID [{results.run_id}]: {results}")

        try:
            # Get the Run ID from the results
            run_id = results.run_id

            # Get the Job from the JOB_STORE
            job: LIFQueryPlannerJob | None = JOB_STORE.get(run_id)
            if not job:
                raise LIFException(f"Job with ID {run_id} not found in JOB_STORE.")

            # Verify the Job status is 'PENDING'
            if job.status != "PENDING":
                raise LIFException(f"Job with ID {run_id} is not in 'PENDING' status, current status: {job.status}")

            # Get the LIF Query from the Job
            lif_query: LIFQuery = job.query

            # Get the LIF fragment paths from the query
            lif_fragment_paths: List[str] = util.get_lif_fragment_paths_from_query(lif_query)

            # Collect all LIF fragments from the results
            fragments: List[LIFFragment] = []
            for part_result in results.query_plan_part_results:
                if part_result.error:
                    logger.error(
                        f"Error in orchestration part result for information source {part_result.information_source_id}: {part_result.error}"
                    )
                else:
                    if part_result.fragments:
                        fragments.extend([fragment for fragment in part_result.fragments if fragment])

            # Send the orchestration results to the LIF Cache service
            lif_query_filter: LIFQueryFilter = lif_query.filter
            lif_fragments: List[LIFFragment] = util.adjust_lif_fragments_for_initial_orchestrator_simplification(
                fragments, lif_fragment_paths
            )

            json_body = {
                "lif_query_filter": lif_query_filter.model_dump(),
                "lif_fragments": [fragment.model_dump() for fragment in lif_fragments],
            }
            async with httpx.AsyncClient() as client:
                response = await client.post(self.lif_cache_save_url, json=json_body)
            response.raise_for_status()

            # Update the associated Job status to 'COMPLETED'
            job.status = "COMPLETED"
            JOB_STORE[run_id] = job
        except httpx.HTTPStatusError as e:
            raise e
        except Exception as e:
            msg = f"LIF Query Planner error: {e}"
            logger.exception(msg)
            raise LIFException(msg) from e


async def query_lif_cache(lif_cache_query_url: str, query: LIFQuery) -> List[LIFRecord]:
    """
    Query the LIF Cache service and return matching LIF records.

    Args:
        lif_cache_query_url (str): The URL of the LIF Cache query endpoint.
        query (LIFQuery): The LIF query to execute.

    Returns:
        List[LIFRecord]: List of matching LIF records.

    Raises:
        LIFException: If the query fails.
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(lif_cache_query_url, json=query.model_dump())
        response.raise_for_status()
        response_json = response.json()
        lif_records = [LIFRecord(**record) for record in response_json]
        logger.info(f"Queried LIF Cache and found {len(lif_records)} records.")
        logger.debug(f"LIF Records: {lif_records}")
        return lif_records
    except httpx.HTTPStatusError as e:
        msg = f"LIF Cache query HTTP error: {e.response.status_code} - {e.response.text}"
        logger.error(msg)
        raise LIFException(msg) from e
    except Exception as e:
        msg = f"LIF Cache query error: {e}"
        logger.error(msg)
        raise LIFException(msg) from e


async def post_orchestrator_job(
    lif_orchestrator_post_url: str, orchestrator_job_request: OrchestratorJobRequest
) -> OrchestratorJobRequestResponse:
    """
    Post an orchestrator job request and return the response.
    Args:
        lif_orchestrator_post_url (str): The URL to post the orchestrator job request to.
        orchestrator_job_request (OrchestratorJobRequest): The orchestrator job request to post.
    Returns:
        OrchestratorJobRequestResponse: The response from the orchestrator job request.
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(lif_orchestrator_post_url, json=orchestrator_job_request.model_dump())
        response.raise_for_status()
        response_json = response.json()
        orchestrator_job_request_response: OrchestratorJobRequestResponse = OrchestratorJobRequestResponse(
            **response_json
        )
        return orchestrator_job_request_response
    except httpx.HTTPStatusError as e:
        msg: str = f"Orchestrator job post HTTP error: {e.response.status_code} - {e.response.text}"
        logger.error(msg)
        raise LIFException(e) from e
    except Exception as e:
        msg = f"Orchestrator job post error: {e}"
        logger.error(msg)
        raise LIFException(msg) from e


class LIFQueryPlannerJob(BaseModel):
    """
    Pydantic model for a LIF Query Planner Job.

    Attributes:
        job_id (str): Unique identifier for the job.
        query (LIFQuery): The query to be executed.
        status (str): Status of the job (e.g., 'pending', 'running', 'completed').
        created_timestamp (str): Timestamp of when the job was created.
        updated_timestamp (str): Timestamp of when the job was last updated.
    """

    job_id: str = Field(..., description="Unique identifier for the job")
    query: LIFQuery = Field(..., description="The query to be executed")
    status: str = Field(..., description="Status of the job (e.g., 'pending', 'running', 'completed')")
    created_timestamp: str = Field(
        ...,
        description="Timestamp of when the job was created",
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )
    updated_timestamp: str = Field(
        ...,
        description="Timestamp of when the job was last updated",
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )


# -------------------------------------------------------------------------
# Temporary in-memory job store
# -------------------------------------------------------------------------
# TODO: update to use Redis
JOB_STORE: Dict[str, LIFQueryPlannerJob] = {}


def prune_job_store() -> None:
    """
    Prune old jobs from the JOB_STORE based on expiry time.

    This function removes jobs that have been in the store longer than JOB_EXPIRY_HOURS.
    It should be called periodically to keep the job store clean.

    Returns:
        None
    """
    try:
        for job_id in list(JOB_STORE.keys())[:-JOB_MAX_CACHE_SIZE]:  # remove all but the last JOB_MAX_CACHE_SIZE jobs
            if JOB_STORE.get(job_id) and util.is_iso_datetime_older_than_x_hours(
                JOB_STORE[job_id].updated_timestamp, JOB_EXPIRY_HOURS
            ):
                logger.info(f"Removing old job {job_id} from JOB_STORE")
                del JOB_STORE[job_id]
    except Exception as e:
        logger.exception(f"Error pruning JOB_STORE: {e}")


# -------------------------------------------------------------------------
# For unit testing
# -------------------------------------------------------------------------
def add_job_to_store(job: LIFQueryPlannerJob) -> None:
    JOB_STORE[job.job_id] = job
