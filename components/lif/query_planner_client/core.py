import os
from typing import AsyncGenerator

import httpx
from lif.exceptions.core import LIFException
from lif.logging import get_logger

logger = get_logger(__name__)

# Default timeout for Query Planner client API calls (in seconds)
DEFAULT_QUERY_PLANNER_CLIENT_TIMEOUT_SECONDS = 30


def _get_query_planner_timeout_seconds() -> int:
    return int(os.getenv("QUERY_PLANNER_CLIENT_TIMEOUT_SECONDS", str(DEFAULT_QUERY_PLANNER_CLIENT_TIMEOUT_SECONDS)))


async def _get_query_planner_client() -> AsyncGenerator[httpx.AsyncClient]:
    """
    Generator that yields an httpx AsyncClient.

    Allows a test harness to override this method to connect to an in-memory Query Planner instance.
    """
    timeout = _get_query_planner_timeout_seconds()
    async with httpx.AsyncClient(timeout=timeout) as client:
        yield client


async def fetch_query_from_query_planner(base_url: str, query: dict) -> list[dict]:
    """POST a LIF query to the Query Planner and return the results.

    Raises:
        QueryPlannerException: on non-200 response, timeout, or connection error.
    """
    # FUTURE WORK: While the CONFIG has a query_planner_query property,
    # It should be folded into this method (or at least this query_planner_client)
    url = base_url.rstrip("/") + "/query"
    logger.info("Calling the Query Planner URL: %s with a timeout of %s", url, _get_query_planner_timeout_seconds())

    try:
        async for client in _get_query_planner_client():
            response = await client.post(url, json=query)
    except httpx.TimeoutException as e:
        msg = f"Query Planner request timed out due to: {e}"
        logger.error(msg)
        raise QueryPlannerException(msg) from e
    except httpx.ConnectError as e:
        msg = f"Failed to connect to Query Planner at {url}: {e}"
        logger.error(msg)
        raise QueryPlannerException(msg) from e

    if response.status_code != 200:
        msg = f"Query Planner returned HTTP {response.status_code}"
        logger.error("%s - %s", msg, response.text)
        raise QueryPlannerException(msg)

    return response.json()


class QueryPlannerException(LIFException):
    """Raised when the Query Planner is unavailable or returns an error."""
