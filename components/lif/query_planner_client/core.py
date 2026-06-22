import httpx
from lif.exceptions.core import LIFException
from lif.logging import get_logger

logger = get_logger(__name__)


async def fetch_query_from_query_planner(base_url: str, query: dict) -> list[dict]:
    """POST a LIF query to the Query Planner and return the results.

    Raises:
        QueryPlannerException: on non-200 response, timeout, or connection error.
    """
    # FUTURE WORK: While the CONFIG has a query_planner_query property,
    # It should be folded into this method (or at least this query_planner_client)
    url = base_url.rstrip("/") + "/query"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=query)
    except httpx.TimeoutException as e:
        msg = f"Query Planner request timed out: {e}"
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
