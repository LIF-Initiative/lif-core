import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends
# from fastapi.middleware.cors import CORSMiddleware

from lif.datatypes import OrchestratorJob, OrchestratorJobRequest, OrchestratorJobRequestResponse
from lif.logging import get_logger
from lif.orchestrator_service.service import OrchestratorService

logger = get_logger(__name__)

# Global service instance
orchestrator_service: Optional[OrchestratorService] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    global orchestrator_service

    logging.getLogger("gql.transport.requests").setLevel(logging.WARNING)  # Reduce noise from gql transport

    orchestrator_service = OrchestratorService(config={})
    logger.info("Orchestrator service initialized")

    yield

    # Cleanup
    logger.info("Shutting down orchestrator service")


app = FastAPI(
    title="Orchestrator API", description="REST API for orchestrator management", version="1.0.0", lifespan=lifespan
)

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )


def get_orchestrator_service() -> OrchestratorService:
    """Dependency to get orchestrator service"""
    if orchestrator_service is None:
        raise HTTPException(status_code=500, detail="Service not initialized")
    return orchestrator_service


@app.post("/jobs", response_model=OrchestratorJobRequestResponse)
async def submit_job(
    job_request: OrchestratorJobRequest, service: OrchestratorService = Depends(get_orchestrator_service)
):
    """Submit a new job to the orchestrator"""
    sources = [part.information_source_id for part in job_request.lif_query_plan.root]
    logger.info(f"Received job request for sources: {sources}")
    try:
        job_id = await service.submit_job(job_request.lif_query_plan)
        return OrchestratorJobRequestResponse(run_id=job_id)
    except Exception as e:
        logger.error(f"Failed to submit job: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/jobs/{job_id}", response_model=OrchestratorJob)
async def get_job_status(job_id: str, service: OrchestratorService = Depends(get_orchestrator_service)):
    """Get the status of a specific job"""
    try:
        return await service.get_job_status(job_id)
    except Exception as e:
        logger.error(f"Failed to get job status: {e}")
        raise HTTPException(status_code=404, detail=str(e))


# @app.delete("/jobs/{job_id}")
# async def cancel_job(
#     job_id: str,
#     orchestrator_type: Optional[str] = None,
#     service: OrchestratorService = Depends(get_orchestrator_service)
# ):
#     """Cancel a specific job"""
#     try:
#         success = await service.cancel_job(job_id, orchestrator_type)
#         if success:
#             return {"message": f"Job {job_id} cancelled successfully"}
#         else:
#             raise HTTPException(status_code=400, detail="Failed to cancel job")
#     except Exception as e:
#         logger.error(f"Failed to cancel job: {e}")
#         raise HTTPException(status_code=500, detail=str(e))


# @app.get("/jobs/{job_id}/result")
# async def get_job_result(
#     job_id: str, timeout: Optional[int] = 30, service: OrchestratorService = Depends(get_orchestrator_service)
# ):
#     """Get the result of a completed job"""
#     try:
#         result = await service.get_job_result(job_id, timeout)
#         if result is not None:
#             return {"job_id": job_id, "result": result}
#         else:
#             raise HTTPException(status_code=404, detail="Job result not found or not ready")
#     except Exception as e:
#         logger.error(f"Failed to get job result: {e}")
#         raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}
