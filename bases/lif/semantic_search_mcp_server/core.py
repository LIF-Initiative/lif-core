"""
LIF Semantic Search MCP Server.

This module provides an MCP (Model Context Protocol) server for semantic search
over LIF data fields. It dynamically loads the schema from MDR at startup
(falling back to file if MDR is unavailable).

Features:
    - Schema loading from MDR with file fallback
    - Dynamic filter and mutation model generation
    - Semantic search over schema leaves
    - Health and status endpoints
    - Schema refresh capability
"""

import os
from typing import Annotated, List

from fastmcp import FastMCP
from pydantic import Field
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse

from lif.lif_schema_config import DEFAULT_ATTRIBUTE_KEYS, LIFSchemaConfig
from lif.logging import get_logger
from lif.schema_state_manager import SchemaStateManager
from lif.semantic_search_service.core import (
    run_mutation,
    run_semantic_search,
)

logger = get_logger(__name__)


# --------- LOAD CONFIGURATION ---------

# Load centralized configuration from environment
CONFIG = LIFSchemaConfig.from_environment()

# Extract values for convenience
DEFAULT_ROOT_NODE = CONFIG.root_type_name
LIF_GRAPHQL_API_URL = os.getenv("LIF_GRAPHQL_API_URL", "http://localhost:8002/graphql")
TOP_K = CONFIG.semantic_search_top_k

ATTRIBUTE_KEYS = DEFAULT_ATTRIBUTE_KEYS


# --------- SCHEMA STATE MANAGER ---------

# Initialize the state manager synchronously at module load time
# This is required because FastMCP tool decorators need the Pydantic models
# to be available at decoration time
_state_manager = SchemaStateManager(CONFIG, attribute_keys=ATTRIBUTE_KEYS)
_state_manager.initialize_sync(force_file=CONFIG.use_openapi_from_file)

# Get the state for use in tool definitions
_state = _state_manager.state

logger.info(
    f"Schema loaded from {_state.source}. "
    f"Total leaves: {len(_state.leaves)}, "
    f"Filter models: {list(_state.filter_models.keys())}"
)

# Get filter and mutation models for the default root type
Filter = _state.filter_models.get(DEFAULT_ROOT_NODE)
MutationModel = _state.mutation_models.get(DEFAULT_ROOT_NODE)

if not Filter:
    raise RuntimeError(f"Filter model not available for root '{DEFAULT_ROOT_NODE}'")


# --------- MCP SERVER SETUP ---------

mcp = FastMCP(name="LIF-Query-Server")


# --------- HTTP ENDPOINTS ---------


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> PlainTextResponse:
    """Health check endpoint for readiness probes."""
    if not _state_manager.is_initialized:
        return PlainTextResponse("NOT_READY", status_code=503)
    return PlainTextResponse("OK")


@mcp.custom_route("/schema/status", methods=["GET"])
async def schema_status(request: Request) -> JSONResponse:
    """Get current schema status and metadata."""
    status = _state_manager.get_status()
    return JSONResponse(status)


@mcp.custom_route("/schema/refresh", methods=["POST"])
async def schema_refresh(request: Request) -> JSONResponse:
    """
    Trigger a schema refresh from MDR.

    Note: This updates the internal state but does NOT update the MCP tool
    definitions, as those are set at module load time. To use new schema
    definitions for tools, the server must be restarted.
    """
    result = await _state_manager.refresh()
    status_code = 200 if result.get("success") else 500

    # Add a note about tool definitions
    if result.get("success"):
        result["note"] = (
            "Schema state updated. Note: MCP tool definitions use the schema "
            "from server startup. Restart the server to use new schema in tools."
        )

    return JSONResponse(result, status_code=status_code)


# --------- MCP TOOLS ---------


@mcp.tool(
    name="lif_query",
    description="Use this tool to run a LIF data query",
    annotations={"title": "Execute LIF Query"},
)
async def lif_query(
    filter: Annotated[Filter, Field(description="Parameters for LIF query")],
    query: Annotated[str, Field(description="Natural language query used to determine LIF data to retrieve")],
) -> List[dict]:
    """Perform a semantic search and retrieve LIF data."""
    # Get current state (may have been refreshed)
    state = _state_manager.state
    return await run_semantic_search(
        filter=filter,
        query=query,
        model=state.model,
        embeddings=state.embeddings,
        leaves=state.leaves,
        top_k=TOP_K,
        graphql_url=LIF_GRAPHQL_API_URL,
        config=CONFIG,
    )


# Only register mutation tool if mutation model is available
if MutationModel:

    @mcp.tool(
        name="lif_mutation",
        description="Use this tool to mutate/update LIF data fields. You must specify a filter to select records.",
        annotations={"title": "Execute LIF Mutation"},
    )
    async def lif_mutation(
        filter: Annotated[Filter, Field(description="Filter to select records for mutation")],
        input: Annotated[MutationModel, Field(description="Fields to update")],
    ) -> dict:
        """Run a mutation on LIF data fields."""
        return await run_mutation(filter=filter, input=input, graphql_url=LIF_GRAPHQL_API_URL)

else:
    logger.warning(f"Mutation model not available for root '{DEFAULT_ROOT_NODE}', lif_mutation tool not registered")


http_app = mcp.http_app()
