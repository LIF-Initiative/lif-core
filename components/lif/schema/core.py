from pathlib import Path
from typing import Any, List, Optional, Union

import jsonref

from lif.datatypes.schema import SchemaField
from lif.logging import get_logger
from lif.string_utils.core import camelcase_path, to_camel_case


logger = get_logger(__name__)


ATTRIBUTE_KEYS = [
    "x-queryable",
    "x-mutable",
    "DataType",
    "Required",
    "Array",
    "UniqueName",
    "enum",
    "type",
]

# ===== SCHEMA FIELD EXTRACTION =====


def extract_nodes(obj: Any, path_prefix: str = "") -> List[SchemaField]:
    """
    Recursively extract schema fields from an OpenAPI/JSON Schema object.

    Returns:
        List[SchemaField]: Flat list of SchemaField objects.
    """
    nodes = []

    def is_array(node: dict) -> bool:
        """Return True if node is an array."""
        return node.get("type") == "array" or "items" in node

    def get_description(node: dict) -> str:
        """Get description from node, prefer lower-case."""
        return node.get("Description", "") or node.get("description", "")

    def extract_attributes(node: dict) -> dict:
        """Extract core attributes from node."""
        attributes = {
            to_camel_case(k): node.get(k) for k in ATTRIBUTE_KEYS if k in node
        }
        if "Array" in node:
            attributes["array"] = node["Array"]
        else:
            attributes["array"] = "Yes" if is_array(node) else "No"
        attributes["type"] = node.get("type", node.get("DataType", None))
        return attributes

    if isinstance(obj, dict):
        key = camelcase_path(path_prefix.rstrip("."))

        branch = (
            "properties" in obj
            and isinstance(obj["properties"], dict)
            and obj["properties"]
        ) or ("items" in obj and isinstance(obj["items"], dict))
        attributes = extract_attributes(obj)
        attributes["branch"] = bool(branch)
        attributes["leaf"] = not attributes["branch"]
        nodes.append(
            SchemaField(
                json_path=key,
                description=get_description(obj),
                attributes=attributes,
            )
        )

        # Recurse children
        if "properties" in obj and isinstance(obj["properties"], dict):
            for prop, val in obj["properties"].items():
                new_prefix = f"{path_prefix}.{prop}" if path_prefix else prop
                nodes.extend(extract_nodes(val, new_prefix))

        if "items" in obj:
            items = obj["items"]
            if isinstance(items, dict):
                nodes.extend(extract_nodes(items, path_prefix))
            elif isinstance(items, list):  # tuple validation
                for sub_item in items:
                    nodes.extend(extract_nodes(sub_item, path_prefix))

    return nodes


# ===== ROOT SCHEMA RESOLUTION =====


def resolve_openapi_root(doc: dict, root: str):
    """Return the schema node for a given root in the OpenAPI spec."""
    candidates = []
    if "components" in doc and "schemas" in doc["components"]:
        schemas = doc["components"]["schemas"]
        if root in schemas:
            return schemas[root], root
        candidates.extend(schemas.keys())
    if "definitions" in doc:
        definitions = doc["definitions"]
        if root in definitions:
            return definitions[root], root
        candidates.extend(definitions.keys())
    raise ValueError(f"Root schema '{root}' not found. Available: {sorted(candidates)}")


# ===== FILE LOADING =====


def load_schema_nodes(
    openapi: Union[str, Path, dict],
    root: Optional[str] = None,
) -> List[SchemaField]:
    """
    Load and extract schema fields from an OpenAPI JSON file, pathlib.Path, or dictionary.

    Args:
        openapi (str | Path | dict): Either a file path (str or Path) to the OpenAPI JSON file,
                                     or a dictionary representing the OpenAPI schema.
        root (str, optional): Root key in the schema to resolve.

    Returns:
        List[SchemaField]: Extracted SchemaField objects.
    """
    if isinstance(openapi, (str, Path)):
        with open(openapi, "r") as f:
            doc = jsonref.load(f)
    elif isinstance(openapi, dict):
        # Replace $ref references in dict input
        doc = jsonref.JsonRef.replace_refs(openapi)
    else:
        raise TypeError("openapi must be a str, Path, or dict")

    node = doc
    path_prefix = ""
    if root:
        node, path_prefix = resolve_openapi_root(doc, root)

    return extract_nodes(node, path_prefix)
