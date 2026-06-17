import httpx
from lif.exceptions.core import LIFException
from lif.logging import get_logger

logger = get_logger(__name__)


async def translate_learner_data(
    base_url: str, source_schema_id: str, target_schema_id: str, learner_data: dict, tenant_schema: str | None = None
) -> dict:
    """POST learner data to the Translator and return the translated result.

    Raises:
        TranslatorException: on non-200 response, timeout, or connection error.
    """
    url = f"{base_url.rstrip('/')}/translate/source/{source_schema_id}/target/{target_schema_id}"
    headers = {"X-API-Tenant-Schema": tenant_schema} if tenant_schema else {}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=learner_data, headers=headers)
    except httpx.TimeoutException as e:
        msg = f"Translator request timed out: {e}"
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
