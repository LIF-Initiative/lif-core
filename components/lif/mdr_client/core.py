import json
import os
from importlib.resources import files
from typing import AsyncGenerator

import httpx
from lif.exceptions.core import LIFException, ResourceNotFoundException
from lif.logging import get_logger

logger = get_logger(__name__)


def _get_mdr_api_url() -> str:
    return os.getenv("LIF_MDR_API_URL", "http://localhost:8012")


def _get_mdr_api_auth_token() -> str:
    return os.getenv("LIF_MDR_API_AUTH_TOKEN", "no_auth_token_set")


async def _get_mdr_client() -> AsyncGenerator[httpx.AsyncClient]:
    """
    Generator that yields an httpx AsyncClient.

    Allows a test harness to override this method to connect to an in-memory MDR instance.
    """
    async with httpx.AsyncClient() as client:
        yield client


def _get_openapi_json_filename() -> str:
    return os.getenv("OPENAPI_JSON_FILENAME", "openapi_constrained_with_interactions.json")


def _get_openapi_data_model_id() -> str | None:
    return os.getenv("OPENAPI_DATA_MODEL_ID")


def _get_use_openapi_from_file() -> bool:
    return os.getenv("USE_OPENAPI_DATA_MODEL_FROM_FILE", "false").lower() == "true"


def _build_mdr_headers() -> dict:
    auth_token = _get_mdr_api_auth_token()
    return {"X-API-Key": auth_token}


def get_openapi_lif_data_model_from_file() -> dict:
    openapi_json_filename: str = _get_openapi_json_filename()
    logger.info(f"Fetching OpenAPI data model from file {openapi_json_filename}")
    resource_path = files("lif.mdr_client.resources") / openapi_json_filename

    with resource_path.open("r", encoding="utf-8") as f:
        return json.load(f)


async def get_openapi_lif_data_model() -> dict | None:
    use_openapi_from_file = _get_use_openapi_from_file()
    openapi_data_model_id = _get_openapi_data_model_id()
    openapi_json_filename: str = _get_openapi_json_filename()
    if not use_openapi_from_file and openapi_data_model_id is None:
        logger.warning(
            "OPENAPI_DATA_MODEL_ID not set. Falling back to fetching OpenAPI data model from file "
            f"{openapi_json_filename}"
        )
        return get_openapi_lif_data_model_from_file()
    if not use_openapi_from_file and openapi_data_model_id is not None:
        logger.info(f"Fetching OpenAPI data model {openapi_data_model_id} from MDR")
        try:
            return await get_data_model_schema(openapi_data_model_id, include_attr_md=True, include_entity_md=False)
        except Exception as e:
            logger.error(f"Failed to fetch OpenAPI data model from MDR: {e}")
            logger.error(f"Falling back to fetching OpenAPI data model from file {openapi_json_filename}")
            return get_openapi_lif_data_model_from_file()
    else:
        return get_openapi_lif_data_model_from_file()


async def get_data_model_schema(
    data_model_id: str, include_attr_md: bool = False, include_entity_md: bool = False
) -> dict:
    mdr_api_url = _get_mdr_api_url()
    url: str = f"{mdr_api_url}/datamodels/open_api_schema/{data_model_id}?include_attr_md={str(include_attr_md).lower()}&include_entity_md={str(include_entity_md).lower()}"
    try:
        async for client in _get_mdr_client():
            response = await client.get(url, headers=_build_mdr_headers())
        response.raise_for_status()
        response_json = response.json()
        return response_json
    except httpx.HTTPStatusError as e:
        logger.error(f"MDR Client HTTP error: {e.response.status_code} - {e.response.text}")
        if e.response.status_code == 404:
            raise ResourceNotFoundException(
                resource_id=data_model_id, message=f"Data model with ID {data_model_id} not found in MDR."
            )
        else:
            raise e
    except Exception as e:
        msg = f"MDR Client error: {e}"
        logger.error(msg)
        raise MDRClientException(msg)


async def get_data_model_transformation(source_data_model_id: str, target_data_model_id: str) -> dict:
    mdr_api_url = _get_mdr_api_url()
    url: str = f"{mdr_api_url}/transformation_groups/transformations_for_data_models/?source_data_model_id={source_data_model_id}&target_data_model_id={target_data_model_id}&size=1000"
    try:
        async for client in _get_mdr_client():
            response = await client.get(url, headers=_build_mdr_headers())
        response.raise_for_status()
        response_json = response.json()
        logger.info(f"Transformation size fetched from MDR: {response_json['total']}")
        if response_json["total"] == 0:
            # workaround for MDR returning 200 with size 0 instead of 404
            resource_id = f"({source_data_model_id}/{target_data_model_id})"
            message = f"Transformation from {source_data_model_id} to {target_data_model_id} not found in MDR."
            raise ResourceNotFoundException(resource_id=resource_id, message=message)
        else:
            return response_json
    except ResourceNotFoundException:
        raise
    except httpx.HTTPStatusError as e:
        logger.error(f"MDR Client HTTP error: {e.response.status_code} - {e.response.text}")
        if e.response.status_code == 404:
            resource_id = f"({source_data_model_id}/{target_data_model_id})"
            message = f"Transformation from {source_data_model_id} to {target_data_model_id} not found in MDR."
            raise ResourceNotFoundException(resource_id=resource_id, message=message)
        else:
            raise e
    except Exception as e:
        msg = f"MDR Client error: {e}"
        logger.error(msg)
        raise MDRClientException(msg)


class MDRClientException(LIFException):
    """Base exception for MDR Client errors."""

    def __init__(self, message="MDR Client error occurred"):
        super().__init__(message)
