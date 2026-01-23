"""Pytest configuration and fixtures for integration tests.

These tests verify data consistency across service layers:
MongoDB -> Query Cache -> Query Planner -> GraphQL -> Cross-org
"""

import pytest
from typing import Generator

from utils.ports import OrgPorts, get_org_ports, get_all_org_ids
from utils.sample_data import SampleDataLoader


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "org(org_id): mark test to run only for specific org(s)",
    )
    config.addinivalue_line(
        "markers",
        "layer(name): mark test for a specific service layer",
    )


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add custom command line options."""
    parser.addoption(
        "--org",
        action="append",
        default=[],
        help="Run tests only for specified org(s). Can be used multiple times.",
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
    return SampleDataLoader(
        org_id=org_id,
        sample_data_key=org_ports.sample_data_key,
    )


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
    check_service_available(org_ports.graphql_url, skip_unavailable)


@pytest.fixture
def require_query_cache(org_ports: OrgPorts, skip_unavailable: bool) -> None:
    """Ensure Query Cache is available for the current org."""
    if not org_ports.query_cache_url:
        pytest.skip(f"Query Cache not exposed for {org_ports.org_id}")
    check_service_available(org_ports.query_cache_url, skip_unavailable)


@pytest.fixture
def require_query_planner(org_ports: OrgPorts, skip_unavailable: bool) -> None:
    """Ensure Query Planner is available for the current org."""
    if not org_ports.query_planner_url:
        pytest.skip(f"Query Planner not exposed for {org_ports.org_id}")
    check_service_available(org_ports.query_planner_url, skip_unavailable)
