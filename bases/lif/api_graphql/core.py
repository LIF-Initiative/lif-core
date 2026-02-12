"""
ASGI application generator for OpenAPI-to-GraphQL.

Converts OpenAPI schema definitions to a Strawberry GraphQL API dynamically.
Generates Python types, input filters, enums, and root query objects from OpenAPI JSON schemas.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from strawberry.fastapi import GraphQLRouter

from lif.api_key_auth import ApiKeyAuthMiddleware, ApiKeyConfig
from lif.lif_schema_config import LIFSchemaConfig
from lif.logging import get_logger
from lif.mdr_client import get_openapi_lif_data_model
from lif.openapi_to_graphql.core import generate_graphql_schema

logger = get_logger(__name__)


# Load centralized configuration from environment
CONFIG = LIFSchemaConfig.from_environment()

logger.info(f"LIF_QUERY_PLANNER_URL: {CONFIG.query_planner_base_url}")
logger.info(f"LIF_GRAPHQL_ROOT_TYPE_NAME: {CONFIG.root_type_name}")
logger.info(f"LIF_MDR_API_URL: {CONFIG.mdr_api_url}")


async def fetch_dynamic_graphql_schema(openapi: dict):
    return await generate_graphql_schema(
        openapi=openapi,
        root_type_name=CONFIG.root_type_name,
        query_planner_query_url=CONFIG.query_planner_query_url,
        query_planner_update_url=CONFIG.query_planner_update_url,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    openapi = await get_openapi_lif_data_model()
    schema = await fetch_dynamic_graphql_schema(openapi=openapi)
    logger.info("GraphQL schema successfully created")
    app.include_router(GraphQLRouter(schema, prefix="/graphql"))
    logger.info("GraphQL router successfully created and included in FastAPI app")
    yield


# Load API key auth configuration from environment
# Set GRAPHQL_AUTH__API_KEYS="key1:client1,key2:client2" to enable authentication
auth_config = ApiKeyConfig.from_environment(prefix="GRAPHQL_AUTH")

app = FastAPI(lifespan=lifespan)

# Add API key authentication middleware if configured
if auth_config.is_enabled:
    app.add_middleware(ApiKeyAuthMiddleware, config=auth_config)
    logger.info("API key authentication enabled for GraphQL")
else:
    logger.info("API key authentication not configured (GRAPHQL_AUTH__API_KEYS not set)")
