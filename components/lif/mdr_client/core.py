import json
import os
from importlib.resources import files
from typing import TYPE_CHECKING, AsyncGenerator, Optional

import httpx
from lif.exceptions.core import LIFException, ResourceNotFoundException
from lif.logging import get_logger

if TYPE_CHECKING:
    from lif.lif_schema_config import LIFSchemaConfig

logger = get_logger(__name__)

# Default timeout for MDR API calls (in seconds)
DEFAULT_MDR_TIMEOUT_SECONDS = 30


# =============================================================================
# Legacy env-var based helpers (kept for backward compatibility)
# =============================================================================


def _get_mdr_api_url() -> str:
    return os.getenv("LIF_MDR_API_URL", "http://localhost:8012")


def _get_mdr_api_auth_token() -> str:
    return os.getenv("LIF_MDR_API_AUTH_TOKEN", "no_auth_token_set")


def _get_mdr_timeout_seconds() -> int:
    return int(os.getenv("MDR_TIMEOUT_SECONDS", str(DEFAULT_MDR_TIMEOUT_SECONDS)))


def _get_openapi_json_filename() -> str:
    return os.getenv("OPENAPI_JSON_FILENAME", "openapi_constrained_with_interactions.json")


def _get_openapi_data_model_id() -> str | None:
    return os.getenv("OPENAPI_DATA_MODEL_ID")


def _get_use_openapi_from_file() -> bool:
    return os.getenv("USE_OPENAPI_DATA_MODEL_FROM_FILE", "false").lower() == "true"


def _build_mdr_headers(auth_token: Optional[str] = None) -> dict:
    if auth_token is None:
        auth_token = _get_mdr_api_auth_token()
    return {"X-API-Key": auth_token}


# =============================================================================
# HTTP Client factories
# =============================================================================


async def _get_mdr_client() -> AsyncGenerator[httpx.AsyncClient]:
    """
    Generator that yields an httpx AsyncClient.

    Allows a test harness to override this method to connect to an in-memory MDR instance.
    """
    timeout = _get_mdr_timeout_seconds()
    async with httpx.AsyncClient(timeout=timeout) as client:
        yield client


def _create_sync_client(timeout: int) -> httpx.Client:
    """Create a synchronous httpx Client with the specified timeout."""
    return httpx.Client(timeout=timeout)


# =============================================================================
# File-based schema loading
# =============================================================================


def get_openapi_lif_data_model_from_file(filename: Optional[str] = None) -> dict:
    """
    Load OpenAPI data model from bundled file.

    Args:
        filename: Optional filename to load. Defaults to env var or standard file.

    Returns:
        The OpenAPI schema dictionary
    """
    if filename is None:
        filename = _get_openapi_json_filename()
    logger.info(f"Loading OpenAPI data model from file: {filename}")
    resource_path = files("lif.mdr_client.resources") / filename

    with resource_path.open("r", encoding="utf-8") as f:
        return json.load(f)


# =============================================================================
# Config-based MDR functions (preferred for new code)
# =============================================================================


def fetch_schema_from_mdr(
    config: "LIFSchemaConfig",
    include_attr_md: bool = True,
    include_entity_md: bool = False,
) -> dict:
    """
    Fetch OpenAPI schema from MDR using configuration.

    This is the preferred method for fetching schemas - it uses centralized
    configuration and does NOT fall back to file on failure.

    Args:
        config: LIFSchemaConfig instance with MDR settings
        include_attr_md: Include attribute metadata in response
        include_entity_md: Include entity metadata in response

    Returns:
        The OpenAPI schema dictionary

    Raises:
        MDRClientException: If MDR is unavailable or returns an error
        MDRConfigurationError: If OPENAPI_DATA_MODEL_ID is not configured
        ResourceNotFoundException: If the data model is not found
    """
    if not config.openapi_data_model_id:
        raise MDRConfigurationError(
            "OPENAPI_DATA_MODEL_ID must be set when USE_OPENAPI_DATA_MODEL_FROM_FILE is false. "
            "Either set OPENAPI_DATA_MODEL_ID or set USE_OPENAPI_DATA_MODEL_FROM_FILE=true."
        )

    url = (
        f"{config.mdr_api_url}/datamodels/open_api_schema/{config.openapi_data_model_id}"
        f"?include_attr_md={str(include_attr_md).lower()}"
        f"&include_entity_md={str(include_entity_md).lower()}"
    )

    headers = _build_mdr_headers(config.mdr_api_auth_token)

    logger.info(f"Fetching OpenAPI schema from MDR: {config.openapi_data_model_id}")

    try:
        with _create_sync_client(config.mdr_timeout_seconds) as client:
            response = client.get(url, headers=headers)
        response.raise_for_status()
        logger.info("Successfully loaded OpenAPI schema from MDR")
        return response.json()

    except httpx.TimeoutException as e:
        msg = f"MDR request timed out after {config.mdr_timeout_seconds}s: {e}"
        logger.error(msg)
        raise MDRClientException(msg)

    except httpx.ConnectError as e:
        msg = f"Failed to connect to MDR at {config.mdr_api_url}: {e}"
        logger.error(msg)
        raise MDRClientException(msg)

    except httpx.HTTPStatusError as e:
        logger.error(f"MDR HTTP error: {e.response.status_code} - {e.response.text}")
        if e.response.status_code == 404:
            raise ResourceNotFoundException(
                resource_id=config.openapi_data_model_id,
                message=f"Data model '{config.openapi_data_model_id}' not found in MDR.",
            )
        raise MDRClientException(f"MDR returned HTTP {e.response.status_code}: {e.response.text}")

    except Exception as e:
        msg = f"Unexpected error fetching from MDR: {e}"
        logger.error(msg)
        raise MDRClientException(msg)


def load_openapi_schema(config: "LIFSchemaConfig") -> tuple[dict, str]:
    """
    Load OpenAPI schema based on configuration.

    Uses file if USE_OPENAPI_DATA_MODEL_FROM_FILE is true, otherwise fetches from MDR.
    Does NOT fall back to file if MDR fails - this prevents silent use of stale data.

    Args:
        config: LIFSchemaConfig instance

    Returns:
        Tuple of (openapi_dict, source) where source is "mdr" or "file"

    Raises:
        MDRClientException: If MDR is configured but unavailable
        MDRConfigurationError: If MDR is expected but not properly configured
    """
    if config.use_openapi_from_file:
        logger.info("USE_OPENAPI_DATA_MODEL_FROM_FILE=true, loading from bundled file")
        return get_openapi_lif_data_model_from_file(config.openapi_json_filename), "file"

    # MDR is expected - fetch it (will raise on failure, no fallback)
    return fetch_schema_from_mdr(config), "mdr"


# =============================================================================
# Legacy sync functions (kept for backward compatibility)
# =============================================================================


def get_data_model_schema_sync(
    data_model_id: str,
    include_attr_md: bool = False,
    include_entity_md: bool = False,
    timeout: Optional[int] = None,
) -> dict:
    """
    Synchronous version of get_data_model_schema using env vars.

    DEPRECATED: Prefer fetch_schema_from_mdr() with LIFSchemaConfig.

    Args:
        data_model_id: The MDR data model ID to fetch
        include_attr_md: Include attribute metadata in response
        include_entity_md: Include entity metadata in response
        timeout: Optional timeout in seconds

    Returns:
        The OpenAPI schema dictionary

    Raises:
        ResourceNotFoundException: If the data model is not found
        MDRClientException: For other MDR errors
    """
    mdr_api_url = _get_mdr_api_url()
    if timeout is None:
        timeout = _get_mdr_timeout_seconds()

    url = (
        f"{mdr_api_url}/datamodels/open_api_schema/{data_model_id}"
        f"?include_attr_md={str(include_attr_md).lower()}"
        f"&include_entity_md={str(include_entity_md).lower()}"
    )
    try:
        with _create_sync_client(timeout) as client:
            response = client.get(url, headers=_build_mdr_headers())
        response.raise_for_status()
        return response.json()
    except httpx.TimeoutException as e:
        msg = f"MDR Client timeout after {timeout}s: {e}"
        logger.error(msg)
        raise MDRClientException(msg)
    except httpx.HTTPStatusError as e:
        logger.error(f"MDR Client HTTP error: {e.response.status_code} - {e.response.text}")
        if e.response.status_code == 404:
            raise ResourceNotFoundException(
                resource_id=data_model_id,
                message=f"Data model with ID {data_model_id} not found in MDR.",
            )
        else:
            raise e
    except Exception as e:
        msg = f"MDR Client error: {e}"
        logger.error(msg)
        raise MDRClientException(msg)


def get_openapi_lif_data_model_sync(timeout: Optional[int] = None) -> tuple[dict, str]:
    """
    Synchronous schema loading using env vars.

    DEPRECATED: Prefer load_openapi_schema() with LIFSchemaConfig.

    This function falls back to file if MDR fails - use load_openapi_schema()
    for stricter behavior that fails instead of using potentially stale data.

    Args:
        timeout: Optional timeout in seconds for MDR calls

    Returns:
        Tuple of (openapi_dict, source) where source is "mdr" or "file"
    """
    use_openapi_from_file = _get_use_openapi_from_file()
    openapi_data_model_id = _get_openapi_data_model_id()
    openapi_json_filename = _get_openapi_json_filename()

    if use_openapi_from_file:
        logger.info("USE_OPENAPI_DATA_MODEL_FROM_FILE is set, loading from file")
        return get_openapi_lif_data_model_from_file(), "file"

    if openapi_data_model_id is None:
        logger.warning(
            f"OPENAPI_DATA_MODEL_ID not set. Falling back to file {openapi_json_filename}"
        )
        return get_openapi_lif_data_model_from_file(), "file"

    # Try MDR - this legacy function falls back to file on failure
    logger.info(f"Fetching OpenAPI data model {openapi_data_model_id} from MDR")
    try:
        openapi = get_data_model_schema_sync(
            openapi_data_model_id,
            include_attr_md=True,
            include_entity_md=False,
            timeout=timeout,
        )
        logger.info("Successfully loaded OpenAPI data model from MDR")
        return openapi, "mdr"
    except Exception as e:
        logger.error(f"Failed to fetch OpenAPI data model from MDR: {e}")
        logger.warning(f"Falling back to file {openapi_json_filename}")
        return get_openapi_lif_data_model_from_file(), "file"


# =============================================================================
# Async functions (existing API preserved)
# =============================================================================


async def get_openapi_lif_data_model() -> dict | None:
    """
    Async schema loading using env vars.

    Note: This function falls back to file if MDR fails.
    """
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


# =============================================================================
# Exceptions
# =============================================================================


class MDRClientException(LIFException):
    """Base exception for MDR Client errors."""

    def __init__(self, message="MDR Client error occurred"):
        super().__init__(message)


class MDRConfigurationError(MDRClientException):
    """Raised when MDR is not properly configured."""

    def __init__(self, message="MDR configuration error"):
        super().__init__(message)
