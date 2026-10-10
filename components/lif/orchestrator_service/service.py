from typing import Dict, Any
import logging

from lif.datatypes import LIFQueryPlan, OrchestratorJobDefinition, OrchestratorJob
from lif.orchestrator_clients.factory import OrchestratorFactory

logger = logging.getLogger(__name__)


class OrchestratorService:
    def __init__(self, config: Dict[str, Any], orchestrator_type: str = "dagster"):
        self.config = config
        self.orchestrator_type = orchestrator_type
        self.orchestrator_config = config.get("orchestrators", {}).get(orchestrator_type, {})

        self._orchestrator = OrchestratorFactory.create(orchestrator_type, self.orchestrator_config)

        # TODO: Add support for result queue
        # # Initialize result queue if configured
        # queue_config = config.get("result_queue")
        # if queue_config:
        #     self._result_queue = QueueFactory.create_queue(
        #         queue_config.get("type"),
        #         queue_config.get("config", {})
        #     )
        #     self._orchestrator.set_result_queue(self._result_queue)

        # else:
        #     self._result_queue = None

    async def submit_job(self, lif_query_plan: LIFQueryPlan) -> str:
        """Submit a job to the orchestrator"""

        # 1. TODO: Validate the query plan

        # 2.Trigger job execution
        # Convert LIFQueryPlan to job definition format
        # TODO: Support multiple parts in the query plan
        job_definition = OrchestratorJobDefinition(lif_query_plan=lif_query_plan)

        sources = [part.information_source_id for part in lif_query_plan.root]
        logger.info(f"Job definition created for sources: {sources}")

        try:
            job_id = await self._orchestrator.post_job(job_definition)
            logger.info(f"Job {job_id} submitted to {self.orchestrator_type}")

            # 3. Return job ID
            return job_id
        except Exception as e:
            logger.error(f"Failed to submit job to {self.orchestrator_type}: {e}")
            raise

    async def get_job_status(self, job_id: str) -> OrchestratorJob:
        """Get job status from the orchestrator"""
        try:
            return await self._orchestrator.get_job_status(job_id)
        except Exception as e:
            logger.error(f"Failed to get job status for {job_id}: {e}")
            raise

    # async def get_job_result(self, job_id: str, timeout: Optional[int] = 30) -> Optional[Dict[str, Any]]:
    #     """Get job result from queue or orchestrator metadata"""
    #     # if self._result_queue:
    #     #     return await self._get_result_from_queue(job_id, timeout)
    #     # else:
    #     # Fallback to orchestrator metadata
    #     job = await self.get_job_status(job_id)
    #     if job.status in {OrchestratorJobStatus.SUCCESS, OrchestratorJobStatus.FAILED}:
    #         return job.metadata.get("result")
    #     return None

    # async def _get_result_from_queue(self, job_id: str, timeout: Optional[int]) -> Optional[Dict[str, Any]]:
    #     """Get job result from the result queue"""
    #     # This would be implemented with async queue operations
    #     # For now, using a simple polling approach
    #     import time
    #     start_time = time.time()

    #     while timeout is None or (time.time() - start_time) < timeout:
    #         message = self._result_queue.get(f"job_result_{job_id}", timeout=1)
    #         if message:
    #             self._result_queue.ack(f"job_result_{job_id}", message.id)
    #             return message.payload.get("result")

    #         await asyncio.sleep(1)

    #     return None
