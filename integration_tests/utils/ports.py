"""Port configuration for integration tests.

Port mappings are based on deployments/advisor-demo-docker/docker-compose.yml.
Some internal services (query cache, query planner) are not exposed for org2/org3
in the default docker-compose configuration.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class OrgPorts:
    """Port configuration for a single organization's services."""

    org_id: str
    mongodb: int
    graphql: int
    query_cache: Optional[int] = None  # May not be exposed for all orgs
    query_planner: Optional[int] = None  # May not be exposed for all orgs
    sample_data_key: str = ""

    @property
    def mongodb_uri(self) -> str:
        return f"mongodb://localhost:{self.mongodb}"

    @property
    def graphql_url(self) -> str:
        return f"http://localhost:{self.graphql}/graphql"

    @property
    def query_cache_url(self) -> Optional[str]:
        if self.query_cache:
            return f"http://localhost:{self.query_cache}"
        return None

    @property
    def query_planner_url(self) -> Optional[str]:
        if self.query_planner:
            return f"http://localhost:{self.query_planner}"
        return None


# Port configuration per org based on docker-compose.yml
# MongoDB ports: 27017, 27018, 27019
# GraphQL ports: 8010, 8110, 8210
# Query Cache ports: 8001, 8101, 8201
# Query Planner ports: 8002, 8102, 8202
ORG_PORTS = {
    "org1": OrgPorts(
        org_id="org1",
        mongodb=27017,
        graphql=8010,
        query_cache=8001,
        query_planner=8002,
        sample_data_key="advisor-demo-org1",
    ),
    "org2": OrgPorts(
        org_id="org2",
        mongodb=27018,
        graphql=8110,
        query_cache=8101,
        query_planner=8102,
        sample_data_key="advisor-demo-org2",
    ),
    "org3": OrgPorts(
        org_id="org3",
        mongodb=27019,
        graphql=8210,
        query_cache=8201,
        query_planner=8202,
        sample_data_key="advisor-demo-org3",
    ),
}

# Ports that are in use by other services (avoid these for testing)
RESERVED_PORTS = {
    8003,  # lif-semantic-search-mcp-server
    8004,  # lif-advisor-api
    8005,  # lif-orchestrator-api
    8007,  # lif-translator
    8011,  # lif-example-data-source-rest-api
    8012,  # lif-mdr-api
    3000,  # dagster-webserver
    5174,  # lif-advisor-app
}

# Global service URLs (not per-org)
SEMANTIC_SEARCH_PORT = 8003
SEMANTIC_SEARCH_BASE_URL = f"http://localhost:{SEMANTIC_SEARCH_PORT}"
SEMANTIC_SEARCH_HEALTH_URL = f"{SEMANTIC_SEARCH_BASE_URL}/health"
SEMANTIC_SEARCH_STATUS_URL = f"{SEMANTIC_SEARCH_BASE_URL}/schema/status"
SEMANTIC_SEARCH_MCP_URL = f"{SEMANTIC_SEARCH_BASE_URL}/mcp"

MDR_PORT = 8012
MDR_BASE_URL = f"http://localhost:{MDR_PORT}"


def get_org_ports(org_id: str) -> OrgPorts:
    """Get port configuration for a specific organization."""
    if org_id not in ORG_PORTS:
        raise ValueError(f"Unknown org_id: {org_id}. Valid values: {list(ORG_PORTS.keys())}")
    return ORG_PORTS[org_id]


def get_all_org_ids() -> list[str]:
    """Get list of all configured organization IDs."""
    return list(ORG_PORTS.keys())
