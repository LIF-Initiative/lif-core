import os
import yaml
from datetime import datetime
from pathlib import Path
from typing import List

from asyncio import sleep
from fastapi import FastAPI, HTTPException, Response, status

from lif.datatypes import (
    OrchestratorJobResults,
    LIFQuery,
    LIFQueryPlanPartTranslation,
    LIFQueryStatusResponse,
    LIFRecord,
    LIFUpdate,
)
from lif.exceptions.core import LIFException
from lif.logging.core import get_logger
from lif.query_planner_service.core import LIFQueryPlannerService
from lif.query_planner_service.datatypes import LIFQueryPlannerConfig, LIFQueryPlannerInfoSourceConfig

MIN_POLLING_DELAY_SECONDS: int = 1
MAX_POLLING_DELAY_SECONDS: int = 16
DEFAULT_QUERY_TIMEOUT_SECONDS: int = 300
LIF_QUERY_TIMEOUT_SECONDS: int = int(os.getenv("LIF_QUERY_TIMEOUT_SECONDS", str(DEFAULT_QUERY_TIMEOUT_SECONDS)))
DEFAULT_SERVICE_REQUEST_TIMEOUT_SECONDS: int = 10
LIF_SERVICE_REQUEST_TIMEOUT_SECONDS: int = int(
    os.getenv("LIF_SERVICE_REQUEST_TIMEOUT_SECONDS", str(DEFAULT_SERVICE_REQUEST_TIMEOUT_SECONDS))
)

app = FastAPI()
logger = get_logger(__name__)

LIF_CACHE_URL = os.getenv("LIF_QUERY_CACHE_URL", "http://localhost:8001")
LIF_ORCHESTRATOR_URL = os.getenv("LIF_ORCHESTRATOR_URL", "http://localhost:8005")
INFORMATION_SOURCES_CONFIG_PATH = os.getenv(
    "LIF_QUERY_PLANNER_INFORMATION_SOURCES_CONFIG_PATH", "./information_sources_config.yml"
)


def load_information_sources_yaml_config(file_path: str):
    """
    Get the configuration for the LIF Query Planner Service.

    Returns:
        List[LIFQueryPlannerInfoSourceConfig]: List of information source configuration objects.
    """
    path_to_use = file_path
    if file_path.startswith("./"):
        current_script_path = Path(__file__)
        script_directory = current_script_path.parent
        path_to_use = script_directory / file_path

    try:
        with open(path_to_use, "r") as f:
            yaml_config = yaml.safe_load(f)
        logger.info(f"Loaded information sources yaml config: {yaml_config}")
        config: List[LIFQueryPlannerInfoSourceConfig] = []

        information_sources = yaml_config.get("information_sources")
        if information_sources is not None:
            for info_source_config in information_sources:
                try:
                    translation = None
                    if info_source_config.get("translation"):
                        translation = LIFQueryPlanPartTranslation(**info_source_config["translation"])
                    config.append(
                        LIFQueryPlannerInfoSourceConfig(
                            information_source_id=info_source_config["information_source_id"],
                            information_source_organization=info_source_config["information_source_organization"],
                            adapter_id=info_source_config["adapter_id"],
                            ttl_hours=info_source_config["ttl_hours"],
                            lif_fragment_paths=info_source_config["lif_fragment_paths"],
                            translation=translation,
                        )
                    )
                except Exception as e:
                    msg = f"Error parsing information source config: {e}"
                    logger.error(msg)
                    raise LIFException(msg) from e
        return config
    except FileNotFoundError as e:
        msg = f"Information sources config file not found at path: {path_to_use}"
        logger.error(msg)
        raise LIFException(msg) from e
    except Exception as e:
        msg = f"Error loading information sources config: {e}"
        logger.error(msg)
        raise LIFException(msg) from e


config = LIFQueryPlannerConfig(
    lif_cache_url=LIF_CACHE_URL,
    lif_orchestrator_url=LIF_ORCHESTRATOR_URL,
    information_sources_config=load_information_sources_yaml_config(INFORMATION_SOURCES_CONFIG_PATH),
    query_timeout_seconds=LIF_QUERY_TIMEOUT_SECONDS,
    service_request_timeout_seconds=LIF_SERVICE_REQUEST_TIMEOUT_SECONDS,
)
service: LIFQueryPlannerService = LIFQueryPlannerService(config)


@app.get("/")
def root() -> dict:
    return {"message": "Hello World!"}


# -------------------------------------------------------------------------
# Query endpoint - synchronous-only version that handles polling. This is
# temporary, and will be removed soon.
# -------------------------------------------------------------------------
@app.post("/query", status_code=status.HTTP_200_OK, response_model=List[LIFRecord])
async def do_run_query_sync(query: LIFQuery, response: Response) -> List[LIFRecord]:
    logger.info("CALL RECEIVED TO /query (sync) API")
    try:
        result = await service.run_query(query, first_run=True)
        if isinstance(result, LIFQueryStatusResponse):
            logger.info("Query is still processing, entering polling loop")
            start_time = datetime.now()
            delay_in_seconds: int = MIN_POLLING_DELAY_SECONDS
            while result.status == "PENDING":
                # Wait for the query to complete
                if (datetime.now() - start_time).total_seconds() > config.query_timeout_seconds:
                    raise HTTPException(
                        status_code=408, detail=f"Query timed out after {config.query_timeout_seconds} seconds"
                    )
                logger.info(f"Query still pending, waiting for {delay_in_seconds} seconds before polling again")
                await sleep(delay_in_seconds)
                delay_in_seconds = (
                    delay_in_seconds * 2 if delay_in_seconds < MAX_POLLING_DELAY_SECONDS else MAX_POLLING_DELAY_SECONDS
                )
                result = await service.get_query_status(result.query_id)
            if result.status == "COMPLETED":
                logger.info("Query completed successfully, retrieving results")
                result = await service.run_query(query, first_run=False)
                if isinstance(result, list):
                    logger.info(f"Query completed successfully, returning results: {result}")
                    return result
                else:
                    msg: str = f"Query completed but results are not in expected format: {result}"
                    logger.error(msg)
                    raise HTTPException(status_code=500, detail=msg)
            else:
                msg = f"Query failed with status: {result.status}"
                if result.error_message:
                    msg += f" - {result.error_message}"
                logger.error(msg)
                raise HTTPException(status_code=500, detail=msg)
        else:
            return result
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid query")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing query: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------------------------------------------------
# Query endpoint - temporarily using path /query_async, but will be changed
# to /query in the future.
# -------------------------------------------------------------------------
@app.post("/query_async", response_model=List[LIFRecord] | LIFQueryStatusResponse)
async def do_run_query(query: LIFQuery, response: Response) -> List[LIFRecord] | LIFQueryStatusResponse:
    logger.info("CALL RECEIVED TO /query_async API")
    try:
        result = await service.run_query(query, first_run=True)
        if isinstance(result, LIFQueryStatusResponse):
            response.status_code = status.HTTP_202_ACCEPTED
            response.headers["Location"] = f"/query/{result.query_id}/status"
            response.headers["Retry-After"] = "5"  # seconds to wait before polling
            logger.info(f"Query is still processing, returning status response: {result}")
            return result
        else:
            response.status_code = status.HTTP_200_OK
            logger.info(f"Query completed successfully, returning results: {result}")
            return result
    except ValueError:
        raise
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/query/{query_id}/status")
async def do_get_query_status(query_id: str) -> LIFQueryStatusResponse:
    logger.info(f"CALL RECEIVED TO /query/{query_id}/status API")
    try:
        return await service.get_query_status(query_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job ID")
    except Exception as e:
        logger.error(f"Error retrieving job status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/update", response_model=LIFRecord)
async def do_run_update(update: LIFUpdate) -> LIFRecord:
    logger.info("CALL RECEIVED TO /update API")
    try:
        return await service.run_update(update)
    except ValueError:
        raise
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/orchestration/results")
async def post_orchestration_results(results: OrchestratorJobResults):
    logger.info("CALL RECEIVED TO /fragments API")
    try:
        return await service.run_post_orchestration_results(results)
    except ValueError:
        raise
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
