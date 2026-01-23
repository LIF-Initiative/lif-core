"""
LIF Schema Configuration Component.

Provides centralized configuration and utilities for all LIF services
that work with the schema structure.

Modules:
- core: Main LIFSchemaConfig class
- type_mappings: XSD to Python type conversions
- naming: Case conversion and GraphQL naming conventions
- openapi: OpenAPI document structure helpers

Example:
    from lif.lif_schema_config import LIFSchemaConfig

    config = LIFSchemaConfig.from_environment()
    print(config.root_type_name)  # "Person"
    print(config.graphql_query_name)  # "person"
"""

from lif.lif_schema_config.core import (
    LIFSchemaConfig,
    LIFSchemaConfigError,
)
from lif.lif_schema_config.naming import (
    normalize_identifier_type,
    safe_identifier,
    to_camel_case,
    to_graphql_query_name,
    to_mutation_name,
    to_pascal_case,
    to_schema_name,
    to_snake_case,
)
from lif.lif_schema_config.openapi import (
    DEFAULT_ATTRIBUTE_KEYS,
    OpenAPIExtensions,
    OpenAPIPaths,
    get_data_type,
    get_field_description,
    get_schema,
    get_schemas,
    is_array_field,
    is_mutable,
    is_queryable,
    list_schema_names,
    resolve_ref,
)
from lif.lif_schema_config.type_mappings import (
    PYTHON_TO_XSD,
    XSD_TO_PYTHON,
    python_type_for_xsd,
    xsd_type_for_python,
)

__all__ = [
    # Core config
    "LIFSchemaConfig",
    "LIFSchemaConfigError",
    # Type mappings
    "XSD_TO_PYTHON",
    "PYTHON_TO_XSD",
    "python_type_for_xsd",
    "xsd_type_for_python",
    # Naming conventions
    "to_graphql_query_name",
    "to_schema_name",
    "to_mutation_name",
    "to_camel_case",
    "to_pascal_case",
    "to_snake_case",
    "safe_identifier",
    "normalize_identifier_type",
    # OpenAPI helpers
    "OpenAPIPaths",
    "OpenAPIExtensions",
    "DEFAULT_ATTRIBUTE_KEYS",
    "get_schemas",
    "get_schema",
    "list_schema_names",
    "is_queryable",
    "is_mutable",
    "is_array_field",
    "get_field_description",
    "get_data_type",
    "resolve_ref",
]
