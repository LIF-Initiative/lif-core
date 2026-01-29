"""
LIF Schema Configuration Component.

This component provides centralized configuration for all LIF services that work
with the schema, including:
- GraphQL API (bases/lif/api_graphql)
- Semantic Search (bases/lif/semantic_search_mcp_server)
- OpenAPI to GraphQL conversion (components/lif/openapi_to_graphql)
- LIF-to-LIF Adapter (components/lif/data_source_adapters/lif_to_lif_adapter)
- Query Planner (components/lif/query_planner_service)

Benefits:
- Single source of truth for schema configuration
- Validation catches misconfigurations at startup
- Consistent naming conventions across services
- Easy to extend when schema structure changes

Usage:
    from lif.lif_schema_config import LIFSchemaConfig

    # Load from environment
    config = LIFSchemaConfig.from_environment()

    # Access configuration
    print(config.root_type_name)  # "Person"
    print(config.graphql_query_name)  # "person"
    print(config.mutation_name)  # "updatePerson"
"""

import os
from dataclasses import dataclass, field
from typing import List, Optional, Set

from lif.lif_schema_config.naming import to_graphql_query_name, to_mutation_name
from lif.logging import get_logger

logger = get_logger(__name__)


class LIFSchemaConfigError(Exception):
    """Raised when LIF schema configuration is invalid."""

    pass


@dataclass
class LIFSchemaConfig:
    """
    Centralized configuration for LIF schema-dependent services.

    This consolidates configuration previously scattered across:
    - bases/lif/api_graphql/core.py
    - bases/lif/semantic_search_mcp_server/core.py
    - components/lif/openapi_to_graphql/type_factory.py
    - components/lif/mdr_client/core.py

    Attributes:
        # Root Type Configuration
        root_type_name: Primary schema root type that users query directly (e.g., "Person")
        additional_root_types: Other root types in the schema that serve as reference data -
            indexed for search but not directly queryable as standalone entities

        Example configuration:
            root_type_name = "Person"  # Users query: "Find person with ID X"
            additional_root_types = ["Course", "Organization", "Credential"]

            In this setup, Person is the primary queryable entity. Course, Organization,
            and Credential are indexed (for semantic search) but exist only as reference
            data within Person records - you cannot query "Find Organization with ID Y"
            directly. The `reference_data_roots` property returns additional_root_types
            as a Set for convenient membership testing.

        # Query Planner URLs
        query_planner_base_url: Base URL for query planner service
        query_timeout_seconds: Timeout for GraphQL queries

        # MDR Configuration
        mdr_api_url: Master Data Registry API URL
        mdr_api_auth_token: MDR authentication token
        openapi_data_model_id: MDR data model ID (if fetching from MDR)
        openapi_json_filename: Fallback filename for local OpenAPI file
        use_openapi_from_file: Force use of local file instead of MDR

        # Semantic Search Configuration
        semantic_search_model_name: SentenceTransformer model for embeddings
        semantic_search_top_k: Number of results from semantic search
        semantic_search_timeout: Timeout for semantic search GraphQL calls
    """

    # Root Type Configuration
    root_type_name: str = "Person"
    additional_root_types: List[str] = field(
        default_factory=lambda: ["Course", "Organization", "Credential"]
    )

    # Query Planner URLs
    query_planner_base_url: str = "http://localhost:8002"
    query_timeout_seconds: int = 20

    # MDR Configuration
    mdr_api_url: str = "http://localhost:8012"
    mdr_api_auth_token: str = "no_auth_token_set"
    mdr_timeout_seconds: int = 30
    openapi_data_model_id: Optional[str] = None
    openapi_json_filename: str = "openapi_constrained_with_interactions.json"
    use_openapi_from_file: bool = False

    # Semantic Search Configuration
    semantic_search_model_name: str = "all-MiniLM-L6-v2"
    semantic_search_top_k: int = 200
    semantic_search_timeout: int = 300

    def __post_init__(self):
        """Validate configuration after initialization."""
        self.validate()

    def validate(self) -> None:
        """
        Validate the configuration.

        Raises:
            LIFSchemaConfigError: If configuration is invalid.
        """
        errors = []

        # Validate root_type_name is not empty
        if not self.root_type_name:
            errors.append("root_type_name cannot be empty")

        # Validate timeouts are positive
        if self.query_timeout_seconds <= 0:
            errors.append(f"query_timeout_seconds must be positive, got {self.query_timeout_seconds}")
        if self.mdr_timeout_seconds <= 0:
            errors.append(f"mdr_timeout_seconds must be positive, got {self.mdr_timeout_seconds}")
        if self.semantic_search_timeout <= 0:
            errors.append(f"semantic_search_timeout must be positive, got {self.semantic_search_timeout}")
        if self.semantic_search_top_k <= 0:
            errors.append(f"semantic_search_top_k must be positive, got {self.semantic_search_top_k}")

        if errors:
            error_msg = "LIF schema configuration errors:\n  - " + "\n  - ".join(errors)
            logger.error(error_msg)
            raise LIFSchemaConfigError(error_msg)

        logger.info("LIF schema configuration validated successfully")
        logger.debug(f"  Root type: {self.root_type_name}")
        logger.debug(f"  Additional roots (reference data): {self.additional_root_types}")

    @classmethod
    def from_environment(cls) -> "LIFSchemaConfig":
        """
        Load configuration from environment variables.

        Environment Variables:
            LIF_GRAPHQL_ROOT_TYPE_NAME: Primary root type name (default: "Person")
            LIF_GRAPHQL_ROOT_NODES: Comma-separated additional root types (these are reference data)
            LIF_QUERY_PLANNER_URL: Query planner base URL
            LIF_QUERY_TIMEOUT_SECONDS: Query timeout in seconds
            LIF_MDR_API_URL: MDR API URL
            LIF_MDR_API_AUTH_TOKEN: MDR authentication token
            MDR_TIMEOUT_SECONDS: Timeout for MDR API calls (default: 30)
            OPENAPI_DATA_MODEL_ID: MDR data model ID
            OPENAPI_JSON_FILENAME: Local OpenAPI filename
            USE_OPENAPI_DATA_MODEL_FROM_FILE: Use local file instead of MDR
            SEMANTIC_SEARCH__MODEL_NAME: SentenceTransformer model name
            SEMANTIC_SEARCH__TOP_K: Number of semantic search results (or TOP_K)
            SEMANTIC_SEARCH__GRAPHQL_TIMEOUT__READ: Semantic search timeout

        Returns:
            LIFSchemaConfig: Configuration loaded from environment.
        """
        # Parse root types
        root_type_name = os.getenv("LIF_GRAPHQL_ROOT_TYPE_NAME",
                                   os.getenv("LIF_GRAPHQL_ROOT_NODE", "Person"))

        # Parse additional root types (these serve as reference data)
        root_nodes_str = os.getenv("LIF_GRAPHQL_ROOT_NODES", "Course,Organization,Credential")
        additional_root_types = [
            node.strip() for node in root_nodes_str.split(",")
            if node.strip() and node.strip() != root_type_name
        ]

        # Support both new and old env var names for top_k
        top_k = int(os.getenv(
            "SEMANTIC_SEARCH__TOP_K",
            os.getenv("TOP_K", "200")
        ))

        return cls(
            # Root types
            root_type_name=root_type_name,
            additional_root_types=additional_root_types,
            # Query planner
            query_planner_base_url=os.getenv("LIF_QUERY_PLANNER_URL", "http://localhost:8002"),
            query_timeout_seconds=int(os.getenv("LIF_QUERY_TIMEOUT_SECONDS", "20")),
            # MDR
            mdr_api_url=os.getenv("LIF_MDR_API_URL", "http://localhost:8012"),
            mdr_api_auth_token=os.getenv("LIF_MDR_API_AUTH_TOKEN", "no_auth_token_set"),
            mdr_timeout_seconds=int(os.getenv("MDR_TIMEOUT_SECONDS", "30")),
            openapi_data_model_id=os.getenv("OPENAPI_DATA_MODEL_ID"),
            openapi_json_filename=os.getenv(
                "OPENAPI_JSON_FILENAME",
                "openapi_constrained_with_interactions.json"
            ),
            use_openapi_from_file=os.getenv(
                "USE_OPENAPI_DATA_MODEL_FROM_FILE", "false"
            ).lower() == "true",
            # Semantic search
            semantic_search_model_name=os.getenv(
                "SEMANTIC_SEARCH__MODEL_NAME",
                "all-MiniLM-L6-v2"
            ),
            semantic_search_top_k=top_k,
            semantic_search_timeout=int(os.getenv(
                "SEMANTIC_SEARCH__GRAPHQL_TIMEOUT__READ",
                "300"
            )),
        )

    # Computed properties for convenience

    @property
    def graphql_query_name(self) -> str:
        """GraphQL query field name (e.g., 'person' for root 'Person')."""
        # root_type_name is validated to be non-empty, so result will never be None
        result = to_graphql_query_name(self.root_type_name)
        assert result is not None  # Validated in __post_init__
        return result

    @property
    def mutation_name(self) -> str:
        """GraphQL mutation name (e.g., 'updatePerson')."""
        return to_mutation_name(self.root_type_name, "update")

    @property
    def query_planner_query_url(self) -> str:
        """Full URL for query planner query endpoint."""
        return self.query_planner_base_url.rstrip("/") + "/query"

    @property
    def query_planner_update_url(self) -> str:
        """Full URL for query planner update endpoint."""
        return self.query_planner_base_url.rstrip("/") + "/update"

    @property
    def all_root_types(self) -> List[str]:
        """All root types (primary + additional)."""
        return [self.root_type_name] + self.additional_root_types

    @property
    def reference_data_roots(self) -> Set[str]:
        """Root types that are reference data (indexed but not directly queryable).

        All additional_root_types are considered reference data - they exist to
        provide supporting context for the primary root_type_name.
        """
        return set(self.additional_root_types)

    def is_reference_data_root(self, root_name: str) -> bool:
        """Check if a root type is reference data (indexed but not queryable)."""
        return root_name in self.reference_data_roots

    def get_queryable_roots(self) -> List[str]:
        """Get root types that are directly queryable (not reference data)."""
        return [r for r in self.all_root_types if r not in self.reference_data_roots]
