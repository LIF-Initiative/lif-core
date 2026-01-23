import json
import os
import sys
from typing import Annotated, List

from fastmcp import FastMCP
from pydantic import Field
from sentence_transformers import SentenceTransformer
from starlette.requests import Request
from starlette.responses import PlainTextResponse

from lif.lif_schema_config import LIFSchemaConfig, DEFAULT_ATTRIBUTE_KEYS
from lif.logging import get_logger
from lif.mdr_client import get_openapi_lif_data_model_from_file
from lif.openapi_schema_parser import load_schema_leaves
from lif.semantic_search_service.core import (
    build_embeddings,
    run_semantic_search,
    build_dynamic_filter_model,
    build_dynamic_mutation_model,
    run_mutation,
)

logger = get_logger(__name__)


# --------- LOAD CONFIGURATION ---------

# Load centralized configuration from environment
CONFIG = LIFSchemaConfig.from_environment()

# Extract values for convenience
ROOT_NODES = CONFIG.all_root_types
DEFAULT_ROOT_NODE = CONFIG.root_type_name
LIF_GRAPHQL_API_URL = os.getenv("LIF_GRAPHQL_API_URL", "http://localhost:8002/graphql")
TOP_K = CONFIG.semantic_search_top_k
MODEL_NAME = CONFIG.semantic_search_model_name

ATTRIBUTE_KEYS = DEFAULT_ATTRIBUTE_KEYS


# --------- LOAD VECTOR STORE & EMBEDDINGS ---------

# get the OpenAPI specification for the LIF data model from the MDR
openapi = get_openapi_lif_data_model_from_file()

# Load schema leaves for all root nodes
ALL_LEAVES: List = []
LEAVES_BY_ROOT: dict = {}

for root_node in ROOT_NODES:
    try:
        root_leaves = load_schema_leaves(openapi, root_node, attribute_keys=ATTRIBUTE_KEYS)
        LEAVES_BY_ROOT[root_node] = root_leaves
        ALL_LEAVES.extend(root_leaves)
        logger.info(f"Loaded {len(root_leaves)} schema leaves for root '{root_node}'")
    except Exception as e:
        logger.warning(f"Failed to load schema leaves for root '{root_node}': {e}")

if not ALL_LEAVES:
    logger.critical("No schema leaves loaded from any root node")
    sys.exit(1)

logger.info(f"Total schema leaves loaded: {len(ALL_LEAVES)}")

# Build filter and mutation models for each root
FILTER_MODELS: dict = {}
MUTATION_MODELS: dict = {}

for root_node, root_leaves in LEAVES_BY_ROOT.items():
    try:
        filter_model = build_dynamic_filter_model(root_leaves)
        if root_node in filter_model:
            FILTER_MODELS[root_node] = filter_model[root_node]
            logger.info(f"Dynamic Filter Schema for '{root_node}':\n" + json.dumps(filter_model[root_node].model_json_schema(), indent=2))
    except Exception as e:
        logger.warning(f"Failed to build dynamic filter model for '{root_node}': {e}")

    try:
        mutation_model = build_dynamic_mutation_model(root_leaves)
        if root_node in mutation_model:
            MUTATION_MODELS[root_node] = mutation_model[root_node]
            logger.info(f"Dynamic Mutation Schema for '{root_node}':\n" + json.dumps(mutation_model[root_node].model_json_schema(), indent=2))
    except Exception as e:
        logger.warning(f"Failed to build dynamic mutation model for '{root_node}': {e}")

# Use default root for backwards compatibility
Filter = FILTER_MODELS.get(DEFAULT_ROOT_NODE)
MutationModel = MUTATION_MODELS.get(DEFAULT_ROOT_NODE)

if not Filter:
    logger.critical(f"Failed to build filter model for default root '{DEFAULT_ROOT_NODE}'")
    sys.exit(1)

try:
    MODEL = SentenceTransformer(MODEL_NAME)
except Exception as e:
    logger.critical(f"Failed to load SentenceTransformer model: {e}")
    sys.exit(1)

# ------ ALWAYS embed only the descriptions for ALL leaves (all root entities) ------
EMBEDDING_TEXTS = [leaf.description for leaf in ALL_LEAVES]

try:
    EMBEDDINGS = build_embeddings(EMBEDDING_TEXTS, MODEL)
except Exception as e:
    logger.critical(f"EMBEDDINGS failed: {e}")
    sys.exit(1)

# Keep a reference to all leaves for search
LEAVES = ALL_LEAVES


mcp = FastMCP(name="LIF-Query-Server")


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> PlainTextResponse:
    return PlainTextResponse("OK")


@mcp.tool(
    name="lif_query", description="Use this tool to run a LIF data query", annotations={"title": "Execute LIF Query"}
)
async def lif_query(
    filter: Annotated[Filter, Field(description="Parameters for LIF query")],
    query: Annotated[str, Field(description="Natural language query used to determine LIF data to retrieve")],
) -> List[dict]:
    return await run_semantic_search(
        filter=filter,
        query=query,
        model=MODEL,
        embeddings=EMBEDDINGS,
        leaves=LEAVES,
        top_k=TOP_K,
        graphql_url=LIF_GRAPHQL_API_URL,
        config=CONFIG,
    )


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


http_app = mcp.http_app()
