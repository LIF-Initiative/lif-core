import logging
import traceback

from graphql import GraphQLError
from strawberry import Schema
from strawberry.schema.config import StrawberryConfig
from strawberry.types import ExecutionContext

from lif.openapi_to_graphql.type_factory import (
    build_root_mutation_type,
    build_root_query_type,
    create_input_type,
    create_mutable_input_type,
    create_type,
)

# Strawberry's own logger name, so the records route as they did before.
error_logger = logging.getLogger("strawberry.execution")


class _RedactingSchema(Schema):
    """Logs each GraphQL error's path, type and stack, but not its message or the query (#1351).

    Strawberry's default log quotes the query document, which holds the learner identifier in the
    filter, and the message, which can quote a learner value (graphql-core's serialization errors
    do). What the client receives is unchanged.
    """

    def process_errors(self, errors: list[GraphQLError], execution_context: ExecutionContext | None = None) -> None:
        for error in errors:
            original = error.original_error or error
            stack = "".join(traceback.format_tb(original.__traceback__)).rstrip()
            error_logger.error("GraphQL error at %s: %s\n%s", error.path, type(original).__name__, stack)


def generate_graphql_root_types(
    openapi: dict, root_type_name: str, query_planner_query_url: str, query_planner_update_url: str, created_types: dict
) -> tuple[type, type]:
    """Generates a GraphQL root query type and root mutation type from an OpenAPI dict.

    Args:
        openapi (dict): The OpenAPI specification as a dictionary.
        root_type_name (str): The name of the root type for the GraphQL query.
        query_planner_query_url (str): The URL for a query planner query endpoint
        query_planner_update_url (str): The URL for a query planner update endpoint
        created_types (dict): The dict in which to store types that get created.


    Returns:
        Tuple(type, type): Tuple containing the generated GraphQL root query type and root mutation type.
    """

    schemas = openapi["components"]["schemas"]
    queryable_fields_per_type = {}
    input_types = {}
    mutable_input_types = {}
    input_type_cache = {}  # Per build: keyed by type name alone, so it must not outlive this schema (#1293)
    mutable_input_type_cache = {}  # Add a separate cache for mutable input types

    # First, create all GraphQL types
    for type_name, schema_graph in schemas.items():
        create_type(type_name, schema_graph, openapi, created_types, queryable_fields_per_type)

    # Then, create input/filter types and mutable input types
    for type_name, schema in schemas.items():
        input_class = create_input_type(type_name, schema, openapi, created_types, input_type_cache)
        if input_class:
            input_types[type_name] = input_class

        mutable_input_class = create_mutable_input_type(
            type_name, schema, openapi, created_types, mutable_input_type_cache
        )
        if mutable_input_class:
            mutable_input_types[type_name] = mutable_input_class

    root_query_type = build_root_query_type(root_type_name, created_types, query_planner_query_url, input_types)
    root_mutable_type = build_root_mutation_type(
        root_type_name, created_types, query_planner_update_url, mutable_input_types, input_types
    )
    return root_query_type, root_mutable_type


async def generate_graphql_schema(
    openapi: dict, root_type_name: str, query_planner_query_url: str, query_planner_update_url: str
) -> Schema:
    """Creates and returns an ASGI GraphQL dynamically generated schema.

    This utility function retrieves the OpenAPI specification for the LIF data model,
    generates a GraphQL root query type from it, and constructs a Strawberry GraphQL schema.
    The resulting schema is then used to instantiate and return an ASGI-compatible GraphQL app.

    Args:
        root_type_name (str): The name to use for the GraphQL root query type.
        query_planner_query_url (str): The URL endpoint for the query planner query service.
        query_planner_update_url (str): The URL endpoint for the query planner update service.

    Returns:
        Schema: A Strawberry GraphQL schema instance.

    Raises:
        ValueError: If GraphQL introspection fails.
        FileNotFoundError: If the provided OpenAPI JSON file cannot be found.
        json.JSONDecodeError: If the OpenAPI file is not valid JSON.
    """

    root_query_type, root_mutation_type = generate_graphql_root_types(
        openapi=openapi,
        root_type_name=root_type_name,
        query_planner_query_url=query_planner_query_url,
        query_planner_update_url=query_planner_update_url,
        created_types={},
    )
    schema_graph = _RedactingSchema(
        query=root_query_type, mutation=root_mutation_type, config=StrawberryConfig(auto_camel_case=True)
    )

    return schema_graph
