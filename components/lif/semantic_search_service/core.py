"""
LIF Query Semantic Search Module (Descriptions Only, Centralized Config Check)

This module loads and parses an OpenAPI schema, extracts all leaf node descriptions and attributes into a flat in-memory structure
with all paths and attribute keys in camelCase, and provides an async FastMCP tool to perform semantic and attribute-based
querying over LIF data fields.

Features:
    - Loads required configuration from environment variables.
    - Validates configuration at startup.
    - Loads and parses OpenAPI schema and collects leaf descriptions.
    - Embeds only the leaf descriptions using SentenceTransformer.
    - Provides a FastMCP tool for semantic search and LIF data querying and mutation.
    - No persistent storage: schema is loaded fresh on each run.

TODO: Add an introspection tool to help the LLM understand the relationships
      between branches in the model.
"""

from collections import defaultdict
from enum import Enum
import os
from typing import Annotated, Any, Dict, List, Optional, Tuple, Type

import httpx
import numpy as np
from fastmcp.exceptions import ToolError
from pydantic import BaseModel, Field
from sentence_transformers import SentenceTransformer
from string import Template

from lif.lif_schema_config import LIFSchemaConfig, XSD_TO_PYTHON
from lif.logging import get_logger
from lif.openapi_schema_parser.core import SchemaLeaf
from lif.string_utils import to_value_enum_name

logger = get_logger(__name__)

SEMANTIC_SEARCH_SERVICE__GRAPHQL_TIMEOUT__READ = int(os.getenv("SEMANTIC_SEARCH_SERVICE__GRAPHQL_TIMEOUT__READ", 300))

# Use centralized type mappings from lif_schema_config
DATATYPE_MAP = XSD_TO_PYTHON


# GraphQL Templates
GRAPH_QL_QUERY_TEMPLATE = """
query LIFQuery {
  person(
    filter: $filter
  ) {
    $query
  }
}
"""

GRAPH_QL_MUTATION_TEMPLATE = """
mutation LIFMutation {
  updatePerson(
    filter: $filter,
    input: $input
  ) {
    $fields
  }
}
"""


# build_ functions
def build_embeddings(texts: List[str], model: SentenceTransformer) -> np.ndarray:
    """Compute normalized embeddings for a list of texts.

    Args:
        texts: List of texts to embed.
        model: Pre-loaded SentenceTransformer model.

    Returns:
        Numpy array of embeddings.
    """
    return model.encode(texts, show_progress_bar=False, normalize_embeddings=True)


def build_dynamic_filter_model(schema_leaves: List[SchemaLeaf]) -> Dict[str, Type[BaseModel]]:
    """Build nested Pydantic models for query filtering."""
    tree = {}
    leaf_info = {}
    for leaf in schema_leaves:
        if not leaf.attributes.get("xQueryable", False):
            continue
        parts = leaf.json_path.split(".")
        node = tree
        for i, part in enumerate(parts):
            if part not in node:
                node[part] = {}
            if i == len(parts) - 1:
                leaf_info[tuple(parts)] = leaf
            node = node[part]
    models = {}
    enums = {}

    def make_enum(enum_name: str, values: List[Any]) -> Type[Enum]:
        """Dynamically create a Python Enum."""
        if enum_name in enums:
            return enums[enum_name]
        members = {to_value_enum_name(v): v for v in values}
        enum_cls = Enum(enum_name, members)
        enums[enum_name] = enum_cls
        return enum_cls

    def get_field_type(leaf: "SchemaLeaf", name: str) -> Any:
        """Get field type (enum or base type) for a leaf."""
        if "enum" in leaf.attributes:
            enum_cls = make_enum(name[0].upper() + name[1:], leaf.attributes["enum"])
            return enum_cls
        dt = leaf.attributes.get("dataType", "xsd:string")
        return DATATYPE_MAP.get(dt, str)

    def build_model(name: str, subtree: dict, path: Tuple[str, ...]) -> Optional[Type[BaseModel]]:
        """Recursively create a Pydantic model from schema."""
        fields = {}
        annotations = {}
        for key, child in subtree.items():
            child_path = path + (key,)
            if not child:
                leaf = leaf_info.get(child_path)
                if leaf:
                    field_type = get_field_type(leaf, key)
                    annotations[key] = Annotated[field_type, Field(description=leaf.description)]
                    fields[key] = None
            else:
                child_model = build_model(key[0].upper() + key[1:], child, child_path)
                if child_model is not None:
                    annotations[key] = child_model
                    fields[key] = None
        if not annotations:
            return None
        model_cls = type(
            name[0].upper() + name[1:],
            (BaseModel,),
            {"__annotations__": annotations, "__doc__": f"Data model for {name}.", **fields},
        )
        models[name] = model_cls
        return model_cls

    if not tree:
        return {}
    if len(tree) != 1:
        raise ValueError("All json_path values must share a common root")
    root = next(iter(tree))
    build_model(root[0].upper() + root[1:], tree[root], (root,))
    return models


def build_dynamic_mutation_model(schema_leaves: List[SchemaLeaf]) -> Dict[str, Type[BaseModel]]:
    """Build nested Pydantic models for mutation (x-mutable leaves)."""
    tree = {}
    leaf_info = {}
    for leaf in schema_leaves:
        if not leaf.attributes.get("xMutable", False):
            continue
        parts = leaf.json_path.split(".")
        node = tree
        for i, part in enumerate(parts):
            if part not in node:
                node[part] = {}
            if i == len(parts) - 1:
                leaf_info[tuple(parts)] = leaf
            node = node[part]
    models = {}
    enums = {}

    def make_enum(enum_name: str, values: List[Any]) -> Type[Enum]:
        """Dynamically create a Python Enum."""
        if enum_name in enums:
            return enums[enum_name]
        members = {to_value_enum_name(v): v for v in values}
        enum_cls = Enum(enum_name, members)
        enums[enum_name] = enum_cls
        return enum_cls

    def get_field_type(leaf: "SchemaLeaf", name: str) -> Any:
        """Get field type (enum or base type) for a leaf."""
        if "enum" in leaf.attributes:
            enum_cls = make_enum(name[0].upper() + name[1:], leaf.attributes["enum"])
            return enum_cls
        dt = leaf.attributes.get("dataType", "xsd:string")
        return DATATYPE_MAP.get(dt, str)

    def build_model(name: str, subtree: dict, path: Tuple[str, ...]) -> Optional[Type[BaseModel]]:
        """Recursively create a Pydantic model from schema."""
        fields = {}
        annotations = {}
        for key, child in subtree.items():
            child_path = path + (key,)
            if not child:
                leaf = leaf_info.get(child_path)
                if leaf:
                    field_type = get_field_type(leaf, key)
                    annotations[key] = Annotated[field_type, Field(description=leaf.description)]
                    fields[key] = None
            else:
                child_model = build_model(key[0].upper() + key[1:], child, child_path)
                if child_model is not None:
                    annotations[key] = child_model
                    fields[key] = None
        if not annotations:
            return None
        model_cls = type(
            name[0].upper() + name[1:],
            (BaseModel,),
            {"__annotations__": annotations, "__doc__": f"Mutation data model for {name}.", **fields},
        )
        models[name] = model_cls
        return model_cls

    if not tree:
        return {}
    if len(tree) != 1:
        raise ValueError("All x-mutable json_path values must share a common root")
    root = next(iter(tree))
    build_model(root[0].upper() + root[1:], tree[root], (root,))
    return models


def paths_to_graphql_fields(paths: List[str]) -> str:
    """Convert dotted paths into a nested GraphQL field string."""
    split_paths = [p.split(".") for p in paths]
    if not split_paths:
        return ""
    min_len = min(map(len, split_paths))
    common_root_len = 0
    for i in range(min_len):
        val = split_paths[0][i]
        if all(p[i] == val for p in split_paths):
            common_root_len += 1
        else:
            break
    trimmed_paths = [p[common_root_len:] for p in split_paths]

    def build_tree(paths):
        """Build a nested tree from a list of paths."""
        tree = defaultdict(list)
        for path in paths:
            if path:
                tree[path[0]].append(path[1:])
        return {k: build_tree(v) for k, v in tree.items()}

    def to_graphql(tree, indent=0):
        """Recursively convert a tree to a GraphQL field string."""
        lines = []
        for key, subtree in sorted(tree.items()):
            if subtree:
                lines.append("  " * indent + f"{key} " + "{")
                lines.append(to_graphql(subtree, indent + 1))
                lines.append("  " * indent + "}")
            else:
                lines.append("  " * indent + key)
        return "\n".join(lines)

    tree = build_tree(trimmed_paths)
    return to_graphql(tree)


def to_graphql_literal(obj: Any) -> str:
    """Convert a dict or value to a GraphQL argument literal."""
    from datetime import date, datetime
    from enum import Enum

    if isinstance(obj, dict):
        items = []
        for k, v in obj.items():
            if v is not None:
                items.append(f"{k}: {to_graphql_literal(v)}")
        return "{" + ", ".join(items) + "}"
    elif isinstance(obj, list):
        items = [to_graphql_literal(i) for i in obj]
        return "[" + ", ".join(items) + "]"
    elif isinstance(obj, Enum):
        return obj.name
    elif isinstance(obj, (datetime, date)):
        return f'"{obj.isoformat()}"'
    elif isinstance(obj, str):
        return f'"{obj}"'
    elif isinstance(obj, bool):
        return "true" if obj else "false"
    elif obj is None:
        return "null"
    else:
        return str(obj)


def to_graphql_field_list(obj: Any, indent=0) -> str:
    """Convert a dict to a GraphQL field list (skip None/empty)."""
    INDENT = "  "
    if isinstance(obj, dict):
        fields = []
        for k, v in obj.items():
            if v is None:
                continue
            elif isinstance(v, dict) and v:
                nested = to_graphql_field_list(v, indent + 1)
                if nested.strip():
                    fields.append(f"{INDENT * indent}{k} {{\n{nested}\n{INDENT * indent}}}")
            elif isinstance(v, list) and v and isinstance(v[0], dict):
                nested = to_graphql_field_list(v[0], indent + 1)
                if nested.strip():
                    fields.append(f"{INDENT * indent}{k} {{\n{nested}\n{INDENT * indent}}}")
            elif not isinstance(v, (dict, list)):
                fields.append(f"{INDENT * indent}{k}")
        return "\n".join(fields)
    return ""


def filter_paths_for_graphql(
    paths: List[str],
    config: Optional[LIFSchemaConfig] = None,
) -> List[str]:
    """Filter and transform paths for GraphQL query generation.

    The semantic search indexes multiple root entities (Person, Course, Organization, Credential)
    to improve search relevance. However, the GraphQL person query only returns PersonItem type,
    which has Person fields directly (not wrapped in a "Person" field).

    This function:
    1. Filters out paths from reference data roots (Course, Credential, Organization)
       since they're not valid fields on PersonItem
    2. Strips the primary root prefix (Person.) since PersonItem fields are accessed directly

    Args:
        paths: List of schema paths (e.g., ["Person.name", "Course.identifier"])
        config: LIFSchemaConfig instance (uses defaults if not provided)

    Returns:
        List of paths valid for the GraphQL query
    """
    if config is None:
        config = LIFSchemaConfig()

    primary_root = config.root_type_name
    reference_data_roots = config.reference_data_roots

    filtered_paths = []
    for path in paths:
        if not path:
            continue

        # Get the root of this path
        root = path.split(".")[0] if "." in path else path

        # Skip reference data roots - they help with search but aren't queryable via person
        if root in reference_data_roots:
            logger.debug(f"Filtering out reference data path: {path}")
            continue

        # For Person paths, strip the "Person." prefix since PersonItem fields are direct
        if root == primary_root and "." in path:
            transformed_path = path[len(primary_root) + 1:]  # Strip "Person."
            filtered_paths.append(transformed_path)
        elif root != primary_root:
            # Keep other paths as-is (shouldn't happen with current indexing)
            filtered_paths.append(path)

    return filtered_paths


async def run_semantic_search(
    filter: BaseModel,
    query: str,
    model: SentenceTransformer,
    embeddings: np.ndarray,
    leaves: List[SchemaLeaf],
    top_k: int,
    graphql_url: str,
    config: Optional[LIFSchemaConfig] = None,
):
    """Perform a semantic search and attribute-based lookup on LIF data fields.

    Args:
        filter: LIF filter parameters.
        query: User's natural language search query.
        model: Pre-loaded SentenceTransformer model for embedding.
        embeddings: Pre-computed embeddings for schema leaves.
        leaves: List of schema leaves representing LIF data fields.
        top_k: Number of top results to return.
        graphql_url: Base URL of the GraphQL service to send the LIF query.
        config: LIFSchemaConfig instance (uses defaults if not provided).

    Returns:
        List of search result dictionaries, or an error/result message.

    Raises:
        ToolError: If there is an error during querying.
    """
    q_emb = model.encode([query], normalize_embeddings=True)
    sims = np.dot(embeddings, q_emb.T).flatten()
    idxs = np.argsort(-sims)[:top_k]

    # Log ALL scores for review as needed
    logger.info(f"Similarity scores for query [{query}]:")
    counter = 0
    for i in np.argsort(-sims):
        logger.info(f"{counter}:  {sims[i]:.4f} - {leaves[i].json_path}: {leaves[i].description}")
        counter += 1

    results = []
    for i in idxs:
        leaf = leaves[i]
        out = {"path": leaf.json_path, "score": float(sims[i])}
        out.update(leaf.attributes)
        results.append(out)

    results.sort(key=lambda r: (-r["score"], r["path"]))
    paths = [result.get("path") for result in results]

    # Filter paths for GraphQL query - remove reference data roots and strip Person prefix
    graphql_paths = filter_paths_for_graphql(paths, config=config)
    logger.info(f"Filtered {len(paths)} search paths to {len(graphql_paths)} GraphQL-compatible paths")

    graphql_fields = paths_to_graphql_fields(graphql_paths)

    filter_literal = to_graphql_literal(filter.model_dump())
    query_template = Template(GRAPH_QL_QUERY_TEMPLATE)
    graphql_query = query_template.substitute(filter=filter_literal, query=graphql_fields)
    logger.info(f"Generated GraphQL for query [{query}]:\n{graphql_query}")
    try:
        timeout = httpx.Timeout(connect=5.0, read=SEMANTIC_SEARCH_SERVICE__GRAPHQL_TIMEOUT__READ, write=5.0, pool=5.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(graphql_url, json={"query": graphql_query})
        response.raise_for_status()
        response_json = response.json()
        return [response_json] if response_json else [{"result": "No matches found."}]

    except Exception as e:
        logger.error(f"LIF query tool error: {e}")
        raise ToolError(f"LIF query tool error: {e}")


async def run_mutation(filter: BaseModel, input: BaseModel, graphql_url: str) -> dict:
    filter_literal = to_graphql_literal(filter.model_dump())
    input_literal = to_graphql_literal(input.model_dump())
    fields_literal = to_graphql_field_list(input.model_dump())

    mutation_template = Template(GRAPH_QL_MUTATION_TEMPLATE)
    graphql_mutation = mutation_template.substitute(filter=filter_literal, input=input_literal, fields=fields_literal)

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(graphql_url, json={"query": graphql_mutation})
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"LIF mutation tool error: {e}")
        raise ToolError(f"LIF mutation tool error: {e}")
