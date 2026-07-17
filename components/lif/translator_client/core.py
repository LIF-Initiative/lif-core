import os
from typing import AsyncGenerator

import httpx
from lif.exceptions.core import LIFException
from lif.logging import get_logger

logger = get_logger(__name__)


# Default timeout for Translator client API calls (in seconds)
DEFAULT_TRANSLATOR_CLIENT_TIMEOUT_SECONDS = 30


def _get_translator_timeout_seconds() -> int:
    return int(os.getenv("TRANSLATOR_CLIENT_TIMEOUT_SECONDS", str(DEFAULT_TRANSLATOR_CLIENT_TIMEOUT_SECONDS)))


async def _get_translator_client() -> AsyncGenerator[httpx.AsyncClient]:
    """
    Generator that yields an httpx AsyncClient.

    Allows a test harness to override this method to connect to an in-memory Translator instance.
    """
    timeout = _get_translator_timeout_seconds()
    async with httpx.AsyncClient(timeout=timeout) as client:
        yield client


async def translate_learner_data(
    base_url: str, source_schema_id: str, target_schema_id: str, learner_data: dict, tenant_schema: str | None = None
) -> dict:
    """POST learner data to the Translator and return the translated result.

    Raises:
        TranslatorException: on non-200 response, timeout, or connection error.
    """
    url = f"{base_url.rstrip('/')}/translate/source/{source_schema_id}/target/{target_schema_id}"
    headers = {"X-API-Tenant-Schema": tenant_schema} if tenant_schema else {}
    logger.info("Calling the Translator URL: %s with a timeout of %s", url, _get_translator_timeout_seconds())
    try:
        async for client in _get_translator_client():
            response = await client.post(url, json=learner_data, headers=headers)
    except httpx.TimeoutException as e:
        msg = f"Translator request timed out due to: {e}"
        logger.error(msg)
        raise TranslatorException(msg) from e
    except httpx.ConnectError as e:
        msg = f"Failed to connect to Translator at {url}: {e}"
        logger.error(msg)
        raise TranslatorException(msg) from e

    if response.status_code != 200:
        msg = f"Translator returned HTTP {response.status_code}"
        logger.error("%s - %s", msg, response.text)
        raise TranslatorException(msg)

    return response.json()


class TranslatorException(LIFException):
    """Raised when the Translator is unavailable or returns an error."""
