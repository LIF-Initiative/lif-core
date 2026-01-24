"""
OpenAPI schema structure constants and helpers.

This centralizes OpenAPI document structure knowledge used across:
- openapi_to_graphql/type_factory.py
- openapi_schema_parser/core.py
- mdr_client/core.py

Supports both OpenAPI 3.x (components/schemas) and Swagger 2.x (definitions).
"""

from typing import Any, Dict, List, Optional

from lif.logging import get_logger

logger = get_logger(__name__)


# OpenAPI document structure paths
class OpenAPIPaths:
    """Constants for OpenAPI document structure."""

    # OpenAPI 3.x schema location
    SCHEMAS_PATH = ["components", "schemas"]

    # Swagger 2.x schema location (alternative)
    DEFINITIONS_PATH = ["definitions"]


# Custom OpenAPI extension field names used in LIF schemas
class OpenAPIExtensions:
    """Custom OpenAPI extension fields used in LIF data model."""

    # Marks fields as filterable in GraphQL queries
    QUERYABLE = "x-queryable"

    # Marks fields as updatable in GraphQL mutations
    MUTABLE = "x-mutable"

    # XSD data type specification
    DATA_TYPE = "DataType"

    # Indicates field is an array
    ARRAY = "Array"

    # Field description (supports both cases for backwards compatibility)
    DESCRIPTION = "Description"
    DESCRIPTION_LOWER = "description"

    # Required field marker
    REQUIRED = "Required"

    # Enum values
    ENUM = "enum"


# Default attribute keys to extract from schema leaves
DEFAULT_ATTRIBUTE_KEYS: List[str] = [
    OpenAPIExtensions.QUERYABLE,
    OpenAPIExtensions.MUTABLE,
    OpenAPIExtensions.DATA_TYPE,
    OpenAPIExtensions.REQUIRED,
    OpenAPIExtensions.ARRAY,
    OpenAPIExtensions.ENUM,
]


def _get_nested(doc: Dict[str, Any], path: List[str]) -> Optional[Dict[str, Any]]:
    """Traverse a nested dict by path, returning None if any key is missing."""
    node = doc
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node


def get_schemas(openapi_doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract schemas from an OpenAPI document.

    Supports both OpenAPI 3.x (components/schemas) and Swagger 2.x (definitions).

    Args:
        openapi_doc: Parsed OpenAPI document

    Returns:
        Dictionary of schema name -> schema definition

    Raises:
        ValueError: If no schemas found in document
    """
    # Try OpenAPI 3.x path first
    schemas = _get_nested(openapi_doc, OpenAPIPaths.SCHEMAS_PATH)
    if schemas is not None:
        return schemas

    # Fall back to Swagger 2.x path
    schemas = _get_nested(openapi_doc, OpenAPIPaths.DEFINITIONS_PATH)
    if schemas is not None:
        return schemas

    raise ValueError("No schemas found in OpenAPI document (checked components/schemas and definitions)")


def get_schema(openapi_doc: Dict[str, Any], schema_name: str) -> Dict[str, Any]:
    """
    Get a specific schema by name from an OpenAPI document.

    Args:
        openapi_doc: Parsed OpenAPI document
        schema_name: Name of the schema to retrieve

    Returns:
        Schema definition dictionary

    Raises:
        ValueError: If schema not found
    """
    schemas = get_schemas(openapi_doc)
    if schema_name not in schemas:
        available = sorted(schemas.keys())
        raise ValueError(f"Schema '{schema_name}' not found. Available: {available}")
    return schemas[schema_name]


def list_schema_names(openapi_doc: Dict[str, Any]) -> List[str]:
    """
    List all schema names in an OpenAPI document.

    Args:
        openapi_doc: Parsed OpenAPI document

    Returns:
        Sorted list of schema names
    """
    return sorted(get_schemas(openapi_doc).keys())


def is_queryable(field_def: Dict[str, Any]) -> bool:
    """
    Check if a field definition is marked as queryable.

    Recursively checks nested objects and arrays.

    Args:
        field_def: Field definition from OpenAPI schema

    Returns:
        True if field or any nested field is queryable
    """
    if field_def.get(OpenAPIExtensions.QUERYABLE, False):
        return True

    # Check nested object properties
    if field_def.get("type") == "object" and "properties" in field_def:
        return any(is_queryable(sub_def) for sub_def in field_def["properties"].values())

    # Check array item properties
    if field_def.get("type") == "array" and "properties" in field_def:
        return any(is_queryable(sub_def) for sub_def in field_def["properties"].values())

    return False


def is_mutable(field_def: Dict[str, Any]) -> bool:
    """
    Check if a field definition is marked as mutable.

    Recursively checks nested objects and arrays.

    Args:
        field_def: Field definition from OpenAPI schema

    Returns:
        True if field or any nested field is mutable
    """
    if field_def.get(OpenAPIExtensions.MUTABLE, False):
        return True

    # Check nested object properties
    if field_def.get("type") == "object" and "properties" in field_def:
        return any(is_mutable(sub_def) for sub_def in field_def["properties"].values())

    # Check array item properties
    if field_def.get("type") == "array" and "properties" in field_def:
        return any(is_mutable(sub_def) for sub_def in field_def["properties"].values())

    return False


def is_array_field(field_def: Dict[str, Any]) -> bool:
    """
    Check if a field is an array type.

    Args:
        field_def: Field definition from OpenAPI schema

    Returns:
        True if field is an array
    """
    return field_def.get(OpenAPIExtensions.ARRAY, "No") == "Yes"


def get_field_description(field_def: Dict[str, Any]) -> Optional[str]:
    """
    Get the description from a field definition.

    Supports both "Description" (old schema) and "description" (new schema v2.0).
    Note: In old schema, "description" can be a property name containing an object,
    so we only use lowercase if it's actually a string.

    Args:
        field_def: Field definition from OpenAPI schema

    Returns:
        Field description or None
    """
    # Try PascalCase first (old schema)
    desc = field_def.get(OpenAPIExtensions.DESCRIPTION)
    if desc:
        return desc

    # Try lowercase (new schema v2.0) - only if it's a string
    lowercase_desc = field_def.get(OpenAPIExtensions.DESCRIPTION_LOWER)
    if isinstance(lowercase_desc, str):
        return lowercase_desc

    return None


def get_data_type(field_def: Dict[str, Any], default: str = "xsd:string") -> str:
    """
    Get the XSD data type from a field definition.

    Args:
        field_def: Field definition from OpenAPI schema
        default: Default data type if not specified

    Returns:
        XSD data type string
    """
    return field_def.get(OpenAPIExtensions.DATA_TYPE, default)


def resolve_ref(ref: str, openapi_doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Resolve a JSON reference in an OpenAPI document.

    Args:
        ref: JSON reference string (e.g., "#/components/schemas/Person")
        openapi_doc: Full OpenAPI document

    Returns:
        Referenced schema definition

    Raises:
        KeyError: If reference path is invalid
    """
    path = ref.lstrip("#/").split("/")
    node: Any = openapi_doc
    for part in path:
        node = node[part]
    return node
