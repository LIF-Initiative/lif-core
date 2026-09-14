"""Pytest configuration and fixtures for integration tests.

These tests verify data consistency across service layers:
MongoDB -> Query Cache -> Query Planner -> GraphQL -> Cross-org
"""

import uuid
from typing import Generator, Iterator

import pytest

from utils.ports import OrgPorts, get_org_ports, get_all_org_ids
from utils.sample_data import SampleDataLoader


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers."""
    config.addinivalue_line("markers", "org(org_id): mark test to run only for specific org(s)")
    config.addinivalue_line("markers", "layer(name): mark test for a specific service layer")


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add custom command line options."""
    parser.addoption(
        "--org", action="append", default=[], help="Run tests only for specified org(s). Can be used multiple times."
    )
    parser.addoption(
        "--skip-unavailable",
        action="store_true",
        default=False,
        help="Skip tests for services that aren't reachable instead of failing.",
    )


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Generate test variations for each org when fixture is requested."""
    if "org_id" in metafunc.fixturenames:
        org_filter = metafunc.config.getoption("--org")
        if org_filter:
            org_ids = [o for o in org_filter if o in get_all_org_ids()]
        else:
            org_ids = get_all_org_ids()
        metafunc.parametrize("org_id", org_ids)


@pytest.fixture
def org_ports(org_id: str) -> OrgPorts:
    """Get port configuration for the current org."""
    return get_org_ports(org_id)


@pytest.fixture
def sample_data(org_id: str, org_ports: OrgPorts) -> SampleDataLoader:
    """Load sample data for the current org."""
    return SampleDataLoader(org_id=org_id, sample_data_key=org_ports.sample_data_key)


@pytest.fixture
def skip_unavailable(request: pytest.FixtureRequest) -> bool:
    """Check if --skip-unavailable flag is set."""
    return request.config.getoption("--skip-unavailable")


@pytest.fixture(scope="session")
def mongodb_client() -> Generator:
    """Create a MongoDB client for the session.

    Note: This creates a fresh client. Each test should use the
    appropriate connection string for its org.
    """
    try:
        from pymongo import MongoClient
    except ImportError:
        pytest.skip("pymongo not installed. Run: pip install pymongo")
        return

    # Client will be configured per-test with the right URI
    yield MongoClient

    # No cleanup needed - MongoClient is context-managed per-test


@pytest.fixture(scope="session")
def http_client() -> Generator:
    """Create an HTTP client for the session."""
    try:
        import httpx
    except ImportError:
        pytest.skip("httpx not installed. Run: pip install httpx")
        return

    with httpx.Client(timeout=30.0) as client:
        yield client


def check_service_available(url: str, skip_if_unavailable: bool) -> bool:
    """Check if a service is available, optionally skipping the test."""
    import httpx

    try:
        response = httpx.get(url, timeout=5.0)
        return response.status_code < 500
    except httpx.RequestError:
        if skip_if_unavailable:
            pytest.skip(f"Service not available at {url}")
        return False


def require_service(url: str, name: str, skip_if_unavailable: bool) -> None:
    """Skip or fail cleanly when a service is unreachable.

    The `require_*` fixtures used to call check_service_available() and discard its
    result, so with a service down and --skip-unavailable off the test ran anyway and
    died on a raw httpx.ConnectError from inside the assertion. Reporting it here says
    which service is missing instead.
    """
    if not check_service_available(url, skip_if_unavailable):
        pytest.fail(f"{name} not available at {url}")


@pytest.fixture
def require_mongodb(org_ports: OrgPorts, skip_unavailable: bool) -> None:
    """Ensure MongoDB is available for the current org."""
    import socket

    try:
        sock = socket.create_connection(("localhost", org_ports.mongodb), timeout=5)
        sock.close()
    except (socket.timeout, ConnectionRefusedError, OSError):
        if skip_unavailable:
            pytest.skip(f"MongoDB not available at port {org_ports.mongodb}")
        else:
            pytest.fail(f"MongoDB not available at port {org_ports.mongodb}")


@pytest.fixture
def require_graphql(org_ports: OrgPorts, skip_unavailable: bool) -> None:
    """Ensure GraphQL API is available for the current org."""
    require_service(org_ports.graphql_url, "GraphQL API", skip_unavailable)


@pytest.fixture
def require_query_cache(org_ports: OrgPorts, skip_unavailable: bool) -> None:
    """Ensure Query Cache is available for the current org."""
    if not org_ports.query_cache_url:
        pytest.skip(f"Query Cache not exposed for {org_ports.org_id}")
    require_service(org_ports.query_cache_url, "Query Cache", skip_unavailable)


@pytest.fixture
def require_query_planner(org_ports: OrgPorts, skip_unavailable: bool) -> None:
    """Ensure Query Planner is available for the current org."""
    if not org_ports.query_planner_url:
        pytest.skip(f"Query Planner not exposed for {org_ports.org_id}")
    require_service(org_ports.query_planner_url, "Query Planner", skip_unavailable)


@pytest.fixture
def require_semantic_search(skip_unavailable: bool) -> None:
    """Ensure Semantic Search MCP server is available."""
    from utils.ports import SEMANTIC_SEARCH_HEALTH_URL

    require_service(SEMANTIC_SEARCH_HEALTH_URL, "Semantic Search MCP server", skip_unavailable)


@pytest.fixture
def write_test_identifier(org_ports: OrgPorts, require_query_cache: None) -> Iterator[str]:
    """A person identifier unique to one test, with the documents it creates removed after.

    The write-path tests (#1200) mutate the same MongoDB the read-path tests assert
    against. Two things keep that safe: every identifier is synthetic and unique, so no
    seeded person is touched; and the surrounding suites assert "at least" counts rather
    than exact ones, so an extra document in flight cannot fail them.

    Cleanup goes direct to MongoDB because the Query Cache exposes no delete route. It is
    best-effort: the compose file mounts no volume for mongodb-org*, so a container
    restart reseeds from scratch regardless.
    """
    identifier = f"{uuid.uuid4().hex[:12]}"
    yield f"it1200-{identifier}"

    try:
        from pymongo import MongoClient
    except ImportError:  # pragma: no cover - cleanup is best-effort
        return

    try:
        with MongoClient(org_ports.mongodb_uri, serverSelectionTimeoutMS=5000) as client:
            client["LIF"]["person"].delete_many({"Person.Identifier.identifier": f"it1200-{identifier}"})
    except Exception:  # pragma: no cover - never fail a test in teardown
        pass
