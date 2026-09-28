import os

import httpx
from lif.exceptions.core import LIFException
from lif.logging import get_logger

logger = get_logger(__name__)

# Environment-based configuration
LIF_GRAPHQL_API_URL = os.getenv("LIF_GRAPHQL_API_URL", "http://localhost:8000/graphql")
LIF_GRAPHQL_API_KEY = os.getenv("LIF_GRAPHQL_API_KEY", "")
GRAPHQL_TIMEOUT_READ = float(os.getenv("SEMANTIC_SEARCH_SERVICE__GRAPHQL_TIMEOUT__READ", "300"))


# Names this caller in the Query Planner's query statistics; GraphQL forwards it (#1272).
LIF_CLIENT_NAME = "semantic-search-mcp"


def _build_headers(api_key: str = "") -> dict:
    """Build request headers: X-LIF-Client always, X-API-Key if provided."""
    headers = {"X-LIF-Client": LIF_CLIENT_NAME}
    if not api_key:
        api_key = LIF_GRAPHQL_API_KEY
    if api_key:
        headers["X-API-Key"] = api_key
    return headers


async def _post(url: str, json: dict, headers: dict, timeout: httpx.Timeout | None = None) -> httpx.Response:
    """Send a POST request via httpx. Separated for testability."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        return await client.post(url, json=json, headers=headers)


def _raise_on_graphql_errors(body: dict) -> None:
    """Raise if a 2xx body carries GraphQL `errors` (#1292).

    A GraphQL server answers 200 even for a failed operation, so raise_for_status() alone lets it
    through as data. Partial success (`data` and `errors` together) raises too: the only caller
    selects one root field, so a partial answer means a nested field failed, and returning it
    would let that failure read as absent data.
    """
    errors = body.get("errors")
    if errors:
        messages = "; ".join(e.get("message", str(e)) for e in errors)
        msg = f"GraphQL errors: {messages}"
        logger.error(msg)
        raise GraphQLClientException(msg)


async def graphql_query(query: str, url: str = "", api_key: str = "", timeout_read: float = 0) -> dict:
    """Execute a GraphQL query with optional API key auth.

    Args:
        query: GraphQL query string
        url: GraphQL endpoint URL (defaults to LIF_GRAPHQL_API_URL)
        api_key: API key (defaults to LIF_GRAPHQL_API_KEY env var)
        timeout_read: Read timeout in seconds (defaults to GRAPHQL_TIMEOUT_READ)

    Returns:
        Response JSON dict

    Raises:
        GraphQLClientException: On HTTP or connection errors, or a response carrying GraphQL `errors`
    """
    url = url or LIF_GRAPHQL_API_URL
    timeout_read = timeout_read or GRAPHQL_TIMEOUT_READ
    headers = _build_headers(api_key)
    timeout = httpx.Timeout(connect=5.0, read=timeout_read, write=5.0, pool=5.0)

    try:
        response = await _post(url, json={"query": query}, headers=headers, timeout=timeout)
        response.raise_for_status()
        body = response.json()
    except httpx.HTTPStatusError as e:
        msg = f"GraphQL HTTP error {e.response.status_code}: {e.response.text}"
        logger.error(msg)
        raise GraphQLClientException(msg)
    except Exception as e:
        msg = f"GraphQL client error: {e}"
        logger.error(msg)
        raise GraphQLClientException(msg)

    _raise_on_graphql_errors(body)
    return body


async def graphql_mutation(query: str, url: str = "", api_key: str = "") -> dict:
    """Execute a GraphQL mutation with optional API key auth.

    Args:
        query: GraphQL mutation string
        url: GraphQL endpoint URL (defaults to LIF_GRAPHQL_API_URL)
        api_key: API key (defaults to LIF_GRAPHQL_API_KEY env var)

    Returns:
        Response JSON dict

    Raises:
        GraphQLClientException: On HTTP or connection errors, or a response carrying GraphQL `errors`
    """
    url = url or LIF_GRAPHQL_API_URL
    headers = _build_headers(api_key)

    try:
        response = await _post(url, json={"query": query}, headers=headers)
        response.raise_for_status()
        body = response.json()
    except httpx.HTTPStatusError as e:
        msg = f"GraphQL HTTP error {e.response.status_code}: {e.response.text}"
        logger.error(msg)
        raise GraphQLClientException(msg)
    except Exception as e:
        msg = f"GraphQL client error: {e}"
        logger.error(msg)
        raise GraphQLClientException(msg)

    _raise_on_graphql_errors(body)
    return body


class GraphQLClientException(LIFException):
    """Exception for GraphQL client errors."""

    def __init__(self, message="GraphQL client error occurred"):
        super().__init__(message)
