"""
Dynamic Type and Enum Creation for OpenAPI-to-GraphQL Mapping.

This module provides functions to dynamically generate Python and Strawberry GraphQL types,
input filters, and root query types from OpenAPI schemas. It handles mapping of OpenAPI schema data types,
generates GraphQL Enum types, input filters (including nested and x-queryable fields), and constructs root
query types for Strawberry-based GraphQL APIs.

Key Features:
    - OpenAPI to Python/GraphQL type mapping.
    - Dynamic Strawberry Enum and type creation.
    - Recursive, nested filter (input) types for queryable fields.
    - Root query type construction with filter and selection support.
"""

import dataclasses
import enum
import os
import re
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Type, Union, get_args, get_origin

import httpx
import strawberry
from dateutil import parser

from lif.lif_schema_config import (
    XSD_TO_PYTHON,
    is_mutable as schema_is_mutable,
    is_queryable as schema_is_queryable,
    resolve_ref as schema_resolve_ref,
)
from lif.logging import get_logger
from lif.string_utils import (
    convert_dates_to_strings,
    dict_keys_to_camel,
    dict_keys_to_snake,
    safe_identifier,
    to_camel_case,
    to_pascal_case,
)


logger = get_logger(__name__)


LIF_QUERY_TIMEOUT_SECONDS = int(os.getenv("LIF_QUERY_TIMEOUT_SECONDS", "20"))


# === Constants ===

# Use centralized type mappings from lif_schema_config
DATATYPE_MAP = XSD_TO_PYTHON

input_type_cache: Dict[str, Optional[Type[Any]]] = {}


# === Reference Resolution ===


def resolve_ref(ref: str, openapi: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve a JSON reference in the OpenAPI document.

    Delegates to centralized implementation in lif_schema_config.

    Args:
        ref (str): The JSON reference string.
        openapi (Dict[str, Any]): The OpenAPI document.

    Returns:
        Dict[str, Any]: The referenced object in the OpenAPI document.
    """
    return schema_resolve_ref(ref, openapi)


# === Type/Enum Mapping and Queryable Propagation ===


def map_datatype(field_def: dict) -> Type[Any]:
    """Maps an OpenAPI field definition to a Python type.

    Args:
        field_def (dict): The OpenAPI field definition.

    Returns:
        type: Python type, possibly wrapped in List if 'Array' is 'Yes'.
    """
    dt = field_def.get("DataType", "xsd:string")
    array = field_def.get("Array", "No") == "Yes"
    py_type = DATATYPE_MAP.get(dt, str)
    return List[py_type] if array else py_type


def create_enum_type(enum_name: str, values: List[Any], created_types: Dict[str, Type[Any]]) -> Type[Enum]:
    """Dynamically creates a Strawberry Enum type for given values.

    Args:
        enum_name (str): Name for the Enum type.
        values (list): Enum values.
        created_types (dict): Dict of already created types for caching.

    Returns:
        Type[Enum]: The created Strawberry Enum type.
    """
    if enum_name in created_types:
        return created_types[enum_name]
    enum_dict = {}
    used_names = set()
    for v in values:
        key = str(v).upper()
        key = re.sub(r"\W|^(?=\d)", "_", key)
        orig_key = key
        i = 1
        while key in used_names:
            i += 1
            key = f"{orig_key}_{i}"
        used_names.add(key)
        enum_dict[key] = v
    enum_cls = Enum(enum_name, enum_dict)
    strawberry_enum_cls = strawberry.enum(enum_cls)
    created_types[enum_name] = strawberry_enum_cls
    return strawberry_enum_cls


def propagate_queryables_to_parent(
    parent_type: str, field_name: str, child_type: str, queryable_fields_per_type: Dict[str, Dict[str, Type[Any]]]
) -> None:
    """Propagates x-queryable fields from a child type to a parent type."""
    if child_type not in queryable_fields_per_type:
        return
    if parent_type not in queryable_fields_per_type:
        queryable_fields_per_type[parent_type] = {}
    for child_field, child_type_ in queryable_fields_per_type[child_type].items():
        combined = f"{safe_identifier(field_name)}__{child_field}"
        if combined not in queryable_fields_per_type[parent_type]:
            queryable_fields_per_type[parent_type][combined] = child_type_


# === Query Selection Helpers ===


def input_asdict(obj: Any) -> Any:
    """Recursively converts a dataclass input object to a dict.

    Uses Strawberry's type definition to get the original GraphQL field names,
    preserving the schema's case (e.g., Identifier instead of identifier).
    """
    if hasattr(obj, "__dataclass_fields__"):
        result = {}

        # Build a mapping from Python field name to GraphQL field name using Strawberry's type info
        graphql_names = {}
        strawberry_def = getattr(type(obj), "__strawberry_definition__", None) or getattr(
            type(obj), "_type_definition", None
        )
        if strawberry_def and hasattr(strawberry_def, "fields"):
            for f in strawberry_def.fields:
                graphql_names[f.name] = getattr(f, "graphql_name", f.name)

        for field in obj.__dataclass_fields__.values():
            # Use Strawberry's graphql_name if available, else metadata, else Python name
            key = graphql_names.get(field.name, field.metadata.get("graphql_name", field.name))
            value = getattr(obj, field.name)
            if isinstance(value, list):
                value = [input_asdict(item) for item in value]
            elif hasattr(value, "__dataclass_fields__"):
                value = input_asdict(value)
            result[key] = value
        return result
    return obj


def get_fragments_from_info(info: Any) -> Dict[str, Any]:
    """Returns fragments dict from resolver info."""
    return getattr(info, "fragments", {})


def get_selected_field_paths(
    field_nodes: List[Any], fragments: Dict[str, Any], prefix: Optional[List[str]] = None
) -> Set[str]:
    """Returns all selected field paths in the GraphQL query from field nodes.

    Args:
        field_nodes (List[Any]): The GraphQL AST field nodes.
        fragments (Dict[str, Any]): Fragment definitions.
        prefix (Optional[List[str]]): Prefix for paths.

    Returns:
        set: Set of string paths to all selected fields.
    """
    prefix = prefix or []
    prefix = [prefix] if isinstance(prefix, str) else prefix
    paths = set()
    for node in field_nodes:
        if hasattr(node, "selection_set") and node.selection_set:
            for selection in node.selection_set.selections:
                if selection.kind == "field":
                    path = prefix + [selection.name.value]
                    paths.add(".".join(path))
                    paths.update(get_selected_field_paths([selection], fragments, path))
                elif selection.kind == "fragment_spread":
                    fragment = fragments[selection.name.value]
                    paths.update(get_selected_field_paths([fragment], fragments, prefix))
    return paths


def is_queryable(field_def: dict) -> bool:
    """Checks if this field or any nested field is x-queryable.

    Delegates to centralized implementation in lif_schema_config.
    """
    return schema_is_queryable(field_def)


def is_mutable(field_def: dict) -> bool:
    """Checks if this field or any nested field is x-mutable.

    Delegates to centralized implementation in lif_schema_config.
    """
    return schema_is_mutable(field_def)


def convert_enums(obj):
    """Recursively convert enums to their underlying values for JSON serialization."""
    if isinstance(obj, enum.Enum):
        return obj.value
    elif dataclasses.is_dataclass(obj):
        return convert_enums(dataclasses.asdict(obj))
    elif isinstance(obj, dict):
        return {key: convert_enums(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_enums(item) for item in obj]
    elif isinstance(obj, tuple):
        return tuple(convert_enums(item) for item in obj)
    else:
        return obj


# === Main Dynamic Type Creation ===


def create_type(
    name: str,
    schema: dict,
    openapi: dict,
    created_types: Dict[str, Type[Any]],
    queryable_fields_per_type: Dict[str, Dict[str, Type[Any]]],
    path_prefix: str = "",
    parent_type: Optional[str] = None,
) -> Type[Any]:
    """Recursively creates Python/Strawberry types from a JSON schema.

    Args:
        name (str): Name for the new type.
        schema (dict): Schema definition (OpenAPI).
        openapi (dict): The full OpenAPI schema.
        created_types (dict): Previously created types.
        queryable_fields_per_type (dict): Queryable fields mapping for filters.
        path_prefix (str): Optional path prefix for nested types.
        parent_type (Optional[str]): Name of the parent type.

    Returns:
        type: The created Strawberry/Python type.
    """
    if name in created_types:
        return created_types[name]

    if schema.get("type") == "array" and "properties" in schema:
        item_type_name = f"{name}Item"
        item_schema = {"type": "object", "properties": schema["properties"]}
        item_type_class = create_type(item_type_name, item_schema, openapi, created_types, queryable_fields_per_type)
        created_types[name] = List[item_type_class]
        return created_types[name]

    if schema.get("type") == "object" or "properties" in schema:
        properties = schema.get("properties", {})
        if not properties:
            created_types[name] = str
            return str
        placeholder = type(name, (object,), {})
        created_types[name] = placeholder

        annotations: Dict[str, Type[Any]] = {}
        class_fields: Dict[str, Any] = {}
        required_fields = schema.get("required", [])

        for field_name, field_def in properties.items():
            safe_field_name = safe_identifier(field_name)
            # if "enum" in field_def and field_def.get("x-queryable", False):
            if "enum" in field_def:
                enum_type_name = to_pascal_case(name, field_name, "Enum")
                field_type_class = create_enum_type(enum_type_name, field_def["enum"], created_types)
            # elif "enum" in field_def:
            #     field_type_class = map_datatype(field_def)
            elif "$ref" in field_def:
                ref_schema = resolve_ref(field_def["$ref"], openapi)
                ref_type_name = field_def["$ref"].split("/")[-1]
                field_type_class = create_type(
                    ref_type_name, ref_schema, openapi, created_types, queryable_fields_per_type
                )
                if field_def.get("Array", "No") == "Yes":
                    field_type_class = List[field_type_class]
            elif field_def.get("type") == "array" and "properties" in field_def:
                item_type_name = f"{name}_{field_name}_Item"
                item_schema = {"type": "object", "properties": field_def["properties"]}
                item_type_class = create_type(
                    item_type_name, item_schema, openapi, created_types, queryable_fields_per_type
                )
                field_type_class = List[item_type_class]
            elif field_def.get("type") == "object" and "properties" in field_def:
                sub_type_name = f"{name}_{field_name}"
                field_type_class = create_type(
                    sub_type_name, field_def, openapi, created_types, queryable_fields_per_type
                )
            else:
                field_type_class = map_datatype(field_def)

            if field_name not in required_fields:
                field_type_class = Optional[field_type_class]
            annotations[safe_field_name] = field_type_class

            # Always set the GraphQL field name to preserve original schema case (e.g., Identifier, not identifier)
            class_fields[safe_field_name] = strawberry.field(name=field_name, description=field_def.get("Description"))

        placeholder.__annotations__ = annotations
        for field in annotations:
            if field not in class_fields and getattr(annotations[field], "__origin__", None) is Optional:
                setattr(placeholder, field, None)
        for k, v in class_fields.items():
            setattr(placeholder, k, v)
        type_class = strawberry.type(placeholder, description=schema.get("Description"))
        created_types[name] = type_class
        return type_class

    created_types[name] = str
    return str


def create_mutable_input_type(
    type_name: str,
    schema: dict,
    openapi: dict,
    created_types: Dict[str, Type[Any]],
    input_type_cache: Dict[str, Optional[Type[Any]]],
) -> Optional[Type[Any]]:
    """
    Recursively creates a nested Strawberry input type for fields marked as mutable (``x-mutable: true``) in the OpenAPI schema.

    This function inspects the given JSON schema and generates a Strawberry input type class including only those fields that are marked
    as mutable at any level (including within nested objects and arrays). Types are cached to prevent recursion issues and duplicate generation.
    Useful for building GraphQL mutation input types for create/update operations.

    Args:
        type_name (str): The base name for the generated input type.
        schema (dict): The OpenAPI JSON schema definition for the object.
        openapi (dict): The full OpenAPI document (used for resolving references, if necessary).
        created_types (Dict[str, Type[Any]]): A cache of previously created Strawberry types (enums and output types).
        input_type_cache (Dict[str, Optional[Type[Any]]]): A cache of input types to avoid infinite recursion and duplicate work.

    Returns:
        Optional[Type[Any]]: The generated Strawberry input type class if any mutable fields are found, otherwise None.
    """
    cache_key = f"{type_name}Mutable"
    if cache_key in input_type_cache:
        return input_type_cache[cache_key]

    properties = schema.get("properties", {})
    if not properties:
        input_type_cache[cache_key] = None
        return None

    input_class_fields: Dict[str, Any] = {}
    input_annotations: Dict[str, Any] = {}

    for field_name, field_def in properties.items():
        if not is_mutable(field_def):
            continue

        # Use field_name (not to_camel_case) to preserve original schema case (e.g., Identifier)
        safe_field_name = safe_identifier(field_name)
        if field_def.get("type") == "object" and "properties" in field_def:
            nested_type_name = f"{type_name}_{safe_field_name}MutableInput"
            nested_input_type = create_mutable_input_type(
                nested_type_name, field_def, openapi, created_types, input_type_cache
            )
            if nested_input_type is not None:
                input_annotations[safe_field_name] = Optional[nested_input_type]
                input_class_fields[safe_field_name] = strawberry.field(default=None, name=field_name)
        elif field_def.get("type") == "array" and "properties" in field_def:
            nested_type_name = f"{type_name}_{safe_field_name}MutableItemInput"
            nested_input_type = create_mutable_input_type(
                nested_type_name, {"properties": field_def["properties"]}, openapi, created_types, input_type_cache
            )
            if nested_input_type is not None:
                input_annotations[safe_field_name] = Optional[List[nested_input_type]]
                input_class_fields[safe_field_name] = strawberry.field(default=None, name=field_name)
        elif "enum" in field_def and field_def.get("x-mutable", False):
            enum_type_name = to_pascal_case(type_name, field_name, "Enum")
            enum_type = create_enum_type(enum_type_name, field_def["enum"], created_types)
            input_annotations[safe_field_name] = Optional[enum_type]
            input_class_fields[safe_field_name] = strawberry.field(default=None, name=field_name)
        else:
            py_type = map_datatype(field_def)
            input_annotations[safe_field_name] = Optional[py_type]
            input_class_fields[safe_field_name] = strawberry.field(default=None, name=field_name)

    if not input_class_fields:
        input_type_cache[cache_key] = None
        return None

    input_class = type(f"{type_name}MutableInput", (object,), input_class_fields)
    input_class.__annotations__ = input_annotations
    strawberry_input_type = strawberry.input(input_class)
    input_type_cache[cache_key] = strawberry_input_type
    return strawberry_input_type


# === Dataclass Construction: Recursive Conversion ===


def is_strawberry_type(cls: Any) -> bool:
    """Check if a class is a Strawberry type."""
    # Check for Strawberry-specific attributes
    if hasattr(cls, "__strawberry_definition__") or hasattr(cls, "_type_definition"):
        return True
    # Also check if it has __dataclass_fields__ (Strawberry converts to dataclass)
    if hasattr(cls, "__dataclass_fields__"):
        return True
    return False


def is_dataclass_or_strawberry(cls: Any) -> bool:
    """Check if a class is a dataclass or a Strawberry type."""
    return dataclasses.is_dataclass(cls) or is_strawberry_type(cls)


def can_instantiate_with_kwargs(cls: Any) -> bool:
    """Check if a class can be instantiated with keyword arguments (has annotations)."""
    try:
        return hasattr(cls, "__annotations__") and len(cls.__annotations__) > 0
    except Exception:
        return False


def resolve_actual_type(tp):
    """Unwrap Strawberry Optional wrapper but preserve List types.

    We only unwrap StrawberryOptional, not StrawberryList, because we need
    to know when a field is a list so we can process its items.
    """
    # Unwrap Strawberry Optional wrapper only (not List!)
    while True:
        class_name = type(tp).__name__
        # Only unwrap StrawberryOptional, not StrawberryList
        if class_name == "StrawberryOptional":
            if hasattr(tp, "of_type"):
                tp = tp.of_type
            elif hasattr(tp, "_type"):
                tp = tp._type
            else:
                break
        else:
            break

    # Handle StrawberryList - convert to typing.List with the inner type
    class_name = type(tp).__name__
    if class_name == "StrawberryList":
        inner_type = tp.of_type if hasattr(tp, "of_type") else (tp._type if hasattr(tp, "_type") else None)
        if inner_type is not None:
            # Return as a proper typing.List so get_origin works
            return List[resolve_actual_type(inner_type)]

    # Unwrap typing.Optional/Union
    origin = get_origin(tp)
    if origin is Union:
        args = [a for a in get_args(tp) if a is not type(None)]
        if args:
            return resolve_actual_type(args[0])
        else:
            return type(None)
    return tp


# Updated with dateutil for more flexible date parsing for
# The demo but may want to use a more strict parsing in production


def is_datetime_type(tp: Type[Any]) -> bool:
    """Return True if type is datetime."""
    return resolve_actual_type(tp) is datetime


def is_date_type(tp: Type[Any]) -> bool:
    """Return True if type is date."""
    return resolve_actual_type(tp) is date


def convert_to_datetime(value: Any) -> datetime:
    """Convert value to datetime, or raise ValueError if parsing fails."""
    if isinstance(value, str):
        try:
            return parser.parse(value)
        except Exception as e:
            raise ValueError(f"Cannot parse '{value}' as datetime.") from e
    elif isinstance(value, (int, float)):
        return datetime.fromtimestamp(value)
    raise ValueError(f"Cannot convert type {type(value)} to datetime.")


def convert_to_date(value: Any) -> date:
    """Convert value to date, or raise ValueError if parsing fails."""
    if isinstance(value, str):
        try:
            return parser.parse(value).date()
        except Exception as e:
            raise ValueError(f"Cannot parse '{value}' as date.") from e
    elif isinstance(value, (int, float)):
        return date.fromtimestamp(value)
    raise ValueError(f"Cannot convert type {type(value)} to date.")


def dict_to_dataclass(cls: Any, data: Any) -> Any:
    """
    Recursively constructs a dataclass instance from a dict.
    - Handles date/datetime parsing and nested dataclasses/lists.
    - Logs warnings on errors but does not throw, continues best-effort.

    TODO: This should really be more strict but 'best effort' code
        was added when trying to get mutations and enums to work to
        aid in debugging

    """
    if data is None:
        return None

    actual_cls = resolve_actual_type(cls)
    origin = get_origin(actual_cls)

    # Handle list/array types
    if origin in (list, List):
        item_type = get_args(actual_cls)[0]
        # Resolve the item type in case it's a Strawberry wrapper
        resolved_item_type = resolve_actual_type(item_type)
        if isinstance(data, dict):  # Defensive: treat dict as [dict]
            data = [data]
        if isinstance(data, bool):
            logger.warning(f"dict_to_dataclass: Expected a list or dict for {cls}, got bool: {data}. Skipping.")
            return []
        if not isinstance(data, list):
            raise TypeError(f"Expected a list or dict for {cls}, got {type(data)}: {data}")
        result = []
        for item in data:
            try:
                converted = dict_to_dataclass(resolved_item_type, item)
                result.append(converted)
            except Exception as exc:
                logger.warning(f"dict_to_dataclass: Failed to parse list item {item}: {exc}. Skipping.")
        return result

    # Check if this is a type we can handle
    is_known_type = is_dataclass_or_strawberry(actual_cls)
    can_instantiate = can_instantiate_with_kwargs(actual_cls)

    # Handle dataclasses and Strawberry types
    if is_known_type or can_instantiate:
        if not isinstance(data, dict):
            raise TypeError(f"Expected dict for {cls}, got {type(data)}: {data}")

        # Get field info - try dataclasses.fields first, fall back to __annotations__
        field_types = {}
        field_names = []
        if dataclasses.is_dataclass(actual_cls):
            field_types = {f.name: f.type for f in dataclasses.fields(actual_cls)}
            field_names = [f.name for f in dataclasses.fields(actual_cls)]
        elif hasattr(actual_cls, "__annotations__"):
            field_types = actual_cls.__annotations__
            field_names = list(actual_cls.__annotations__.keys())

        instance_data = {}
        for field_name in field_names:
            field_type = field_types.get(field_name)
            value = data.get(field_name, None)
            try:
                if value is not None and field_type is not None:
                    real_type = resolve_actual_type(field_type)
                    origin = get_origin(real_type)
                    if origin in (list, List):
                        item_type = get_args(real_type)[0]
                        # Resolve the item type as well in case it's wrapped
                        resolved_item_type = resolve_actual_type(item_type)
                        if isinstance(value, dict):
                            value = [value]
                        value = [dict_to_dataclass(resolved_item_type, v) for v in value]
                    elif is_dataclass_or_strawberry(real_type) or can_instantiate_with_kwargs(real_type):
                        if isinstance(value, dict):
                            value = dict_to_dataclass(real_type, value)
                    elif is_datetime_type(field_type):
                        value = convert_to_datetime(value)
                    elif is_date_type(field_type):
                        value = convert_to_date(value)
                instance_data[field_name] = value
            except Exception as exc:
                logger.warning(f"dict_to_dataclass: Error in field '{field_name}' of {cls}: {exc}. Field set to None.")
                instance_data[field_name] = None
        try:
            return actual_cls(**instance_data)
        except Exception as exc:
            logger.warning(
                f"dict_to_dataclass: Failed to instantiate {cls} with {instance_data}: {exc}. Returning None."
            )
            return None

    # Fallback for leaf/primitive types
    return data


# === Input (Filter) Type Creation ===


def create_nested_input_type(
    type_name: str,
    schema: dict,
    openapi: dict,
    created_types: Dict[str, Type[Any]],
    input_type_cache: Dict[str, Optional[Type[Any]]],
) -> Optional[Type[Any]]:
    """Recursively creates nested Strawberry input types for queryable filter fields.

    Only includes fields that are x-queryable in this or descendant types, "bubbling" queryable-ness upward.

    Args:
        type_name (str): Name for the input type.
        schema (dict): The JSON schema.
        openapi (dict): The full OpenAPI document.
        created_types (dict): Previously created types.
        input_type_cache (dict): Cache of input types to prevent recursion.

    Returns:
        Optional[type]: Strawberry input type class, or None if no queryable fields exist.
    """
    if type_name in input_type_cache:
        return input_type_cache[type_name]

    properties = schema.get("properties", {})
    if not properties:
        input_type_cache[type_name] = None
        return None

    input_class_fields: Dict[str, Any] = {}
    input_annotations: Dict[str, Any] = {}

    for field_name, field_def in properties.items():
        if not is_queryable(field_def):
            continue

        safe_field_name = safe_identifier(field_name)
        # Use field_name (not to_camel_case) to preserve original schema case (e.g., Identifier)
        if field_def.get("type") == "object" and "properties" in field_def:
            nested_type_name = f"{type_name}_{safe_field_name}Input"
            nested_input_type = create_nested_input_type(
                nested_type_name, field_def, openapi, created_types, input_type_cache
            )
            if nested_input_type is not None:
                input_annotations[safe_field_name] = Optional[nested_input_type]
                input_class_fields[safe_field_name] = strawberry.field(default=None, name=field_name)
        elif field_def.get("type") == "array" and "properties" in field_def:
            nested_type_name = f"{type_name}_{safe_field_name}ItemInput"
            nested_input_type = create_nested_input_type(
                nested_type_name, {"properties": field_def["properties"]}, openapi, created_types, input_type_cache
            )
            if nested_input_type is not None:
                input_annotations[safe_field_name] = Optional[List[nested_input_type]]
                input_class_fields[safe_field_name] = strawberry.field(default=None, name=field_name)
        elif "enum" in field_def and field_def.get("x-queryable", False):
            enum_type_name = to_pascal_case(type_name, field_name, "Enum")
            enum_type = create_enum_type(enum_type_name, field_def["enum"], created_types)
            input_annotations[safe_field_name] = Optional[enum_type]
            input_class_fields[safe_field_name] = strawberry.field(default=None, name=field_name)
        else:
            py_type = map_datatype(field_def)
            input_annotations[safe_field_name] = Optional[py_type]
            input_class_fields[safe_field_name] = strawberry.field(default=None, name=field_name)

    if not input_class_fields:
        input_type_cache[type_name] = None
        return None

    input_class = type(f"{type_name}Input", (object,), input_class_fields)
    input_class.__annotations__ = input_annotations
    strawberry_input_type = strawberry.input(input_class)
    input_type_cache[type_name] = strawberry_input_type
    return strawberry_input_type


def create_input_type(
    type_name: str, schema: dict, openapi: dict, created_types: Dict[str, Type[Any]]
) -> Optional[Type[Any]]:
    """Creates a nested filter input type for a given schema, or None if none is queryable.

    Args:
        type_name (str): Name for the input type.
        schema (dict): The JSON schema.
        openapi (dict): The OpenAPI document.
        created_types (dict): Dictionary of created types.

    Returns:
        Optional[type]: Strawberry input type, or None if nothing queryable.
    """
    return create_nested_input_type(type_name, schema, openapi, created_types, input_type_cache)


# === Root Query Type Construction ===


def build_root_query_type(
    root_name: str,
    created_types: Dict[str, Type[Any]],
    query_planner_query_url: str,
    input_types: Dict[str, Optional[Type[Any]]],
) -> Type[Any]:
    """
    Dynamically creates the root Strawberry GraphQL Query type.

    Args:
        root_name (str): The root type name (e.g., 'Person').
        created_types (Dict[str, type]): Dictionary of output types.
        input_types (Dict[str, type]): Dictionary of input types.

    Returns:
        type: Strawberry GraphQL Query type.
    """
    # The Strawberry/Python type representing the object (e.g., Person)
    type_class = created_types[root_name]
    # The Strawberry input filter type, if any, for this object
    input_class = input_types.get(root_name)
    # The GraphQL field name (lowercase first char)
    field_name = root_name[0].lower() + root_name[1:]

    if input_class:

        async def resolver(self: Any, info: Any, filter: Optional[Any] = None) -> List[Any]:
            """
            Main GraphQL resolver function for the Query.
            Handles building the query, calling the backend API, and
            deserializing the result into dataclasses.
            """
            # Convert the input filter into a dict, handling enums
            # input_asdict now preserves original GraphQL field names (e.g., Identifier)
            filter_dict_raw = input_asdict(filter) if filter else None
            filter_dict = convert_enums(filter_dict_raw) if filter_dict_raw else None
            # Note: removed dict_keys_to_camel since input_asdict now returns correct schema names

            # Gather selection info from the GraphQL query
            # Use PascalCase for the root name since MongoDB documents use PascalCase keys
            root_query_name = info.field_name[0].upper() + info.field_name[1:]  # "person" -> "Person"
            fragments = get_fragments_from_info(info)
            selected_fields = get_selected_field_paths(info.field_nodes, fragments, root_query_name)

            # Structure the query for the backend API
            filter_wrapped = {root_query_name: filter_dict} if filter_dict else None
            query = {"filter": filter_wrapped, "selected_fields": list(selected_fields)}

            logger.info(f"Query: {query}")
            # Make the backend API call
            async with httpx.AsyncClient(timeout=httpx.Timeout(LIF_QUERY_TIMEOUT_SECONDS)) as client:
                response = await client.post(query_planner_query_url, json=query)

            if response.status_code == 200:
                response_json = response.json()
                logger.info(f"Response: {response_json}")
                # Convert all keys to snake_case for Python
                response_snake = dict_keys_to_snake(response_json)

                # Our API might return a list at the top level, with each element a dict with a 'person' key:
                # Example: [{'person': [{...}, {...}, ...]}]
                # Or, sometimes, just {'person': [...]}
                person_list = []
                if isinstance(response_snake, list) and len(response_snake) > 0:
                    # Grab the first dict in the list (typical for some backends)
                    entry = response_snake[0]
                    # If it has a 'person' key, extract it
                    if isinstance(entry, dict) and "person" in entry:
                        people = entry["person"]
                        if isinstance(people, list):
                            # Most common case: a list of person dicts
                            person_list = people
                        elif isinstance(people, dict):
                            # Handle single person object
                            person_list = [people]
                elif isinstance(response_snake, dict) and "person" in response_snake:
                    # Handle case where response is just a dict with 'person' key
                    people = response_snake["person"]
                    if isinstance(people, list):
                        person_list = people
                    elif isinstance(people, dict):
                        person_list = [people]
                else:
                    # Fallback for unexpected shapes
                    person_list = []

                # Convert the list of dicts into dataclass instances
                result_objs = [dict_to_dataclass(type_class, d) for d in person_list]
                if len(result_objs) > 0 and isinstance(result_objs[0], list):
                    logger.warning("Result objects is list nested in list. Will return inner list.")
                    result_objs = result_objs[0]
                # print(f"Result objects: {result_objs}")
                return result_objs
            else:
                # Log error if the backend request fails
                logger.error(f"Query failed: {response.status_code} {response.text}")
                return []

        is_nested_list: bool = type_class._name == "List"
        return_type = type_class if is_nested_list else List[type_class]
        # Add type annotations for Strawberry's introspection
        resolver.__annotations__ = {
            "self": object,
            "info": object,
            "filter": Optional[input_class],
            "return": return_type,
        }
        # Register the resolver with Strawberry
        strawberry_resolver = strawberry.field(resolver)
        query_fields = {field_name: strawberry_resolver}
        query_annotations = {field_name: return_type}
    else:
        # If there's no filter input, provide a stub resolver (could be expanded)
        @strawberry.field
        def resolver(self: Any, info: Any) -> List[Any]:
            """Default resolver for types without input filters."""
            logger.info("Other type resolution")
            return []

        query_fields = {field_name: resolver}
        query_annotations = {field_name: List[type_class]}

    # Dynamically create the Query class with the annotated fields
    QueryClass = type("Query", (object,), query_fields)
    QueryClass.__annotations__ = query_annotations
    return strawberry.type(QueryClass, name="Query")


def build_root_mutation_type(
    root_name: str,
    created_types: Dict[str, Type[Any]],
    query_planner_update_url: str,
    mutable_input_types: Dict[str, Optional[Type[Any]]],
    input_types: Dict[str, Optional[Type[Any]]] = None,  # You may need this!
) -> Type[Any]:
    type_class = created_types[root_name]
    input_class = mutable_input_types.get(root_name)
    filter_class = None
    if input_types is not None:
        filter_class = input_types.get(root_name)
    else:
        filter_class = None

    mutation_fields = {}

    # ---- UPDATE mutation ----
    update_field_name = f"update{root_name}"

    async def update_resolver(self, info, filter: Any, input: Any) -> Any:
        # input_asdict now preserves original GraphQL field names (e.g., Identifier)
        filter_dict_raw = input_asdict(filter)
        filter_dict = convert_enums(filter_dict_raw)
        # Note: removed dict_keys_to_camel since input_asdict now returns correct schema names

        input_dict_raw = input_asdict(input)
        input_dict = convert_enums(input_dict_raw)
        # Note: removed dict_keys_to_camel since input_asdict now returns correct schema names
        input_dict = convert_dates_to_strings(input_dict)

        # Wrap the dict under 'Person' (PascalCase to match MongoDB document keys)
        filter_wrapped = {"Person": filter_dict} if filter_dict else {}
        input_wrapped = {"Person": input_dict} if input_dict else {}

        root_mutation_name = info.field_name
        payload = {root_mutation_name: {"filter": filter_wrapped, "input": input_wrapped}}
        logger.info(f"Update mutation payload: {payload}")

        async with httpx.AsyncClient() as client:
            response = await client.post(query_planner_update_url, json=payload)
        # ... handle response as in create ...
        if response.status_code == 200:
            response_json = response.json()
            response_snake = dict_keys_to_snake(response_json)
            obj_data = None
            if isinstance(response_snake, dict) and "person" in response_snake:
                people = response_snake["person"]
                if isinstance(people, list) and len(people) > 0:
                    obj_data = people[0]
                elif isinstance(people, dict):
                    obj_data = people
            elif isinstance(response_snake, list) and len(response_snake) > 0:
                entry = response_snake[0]
                if isinstance(entry, dict) and "person" in entry:
                    people = entry["person"]
                    if isinstance(people, list) and len(people) > 0:
                        obj_data = people[0]
                    elif isinstance(people, dict):
                        obj_data = people
            else:
                logger.warning("Unexpected mutation response shape: %s", response_snake)

            if obj_data:
                return dict_to_dataclass(type_class, obj_data)
            else:
                raise Exception("Mutation succeeded but response missing object.")
        else:
            logger.error(f"Mutation failed: {response.status_code} {response.text}")
            raise Exception(f"Mutation failed: {response.status_code}: {response.text}")

    update_resolver.__annotations__ = {
        "self": object,
        "info": object,
        "filter": filter_class,
        "input": input_class,
        "return": type_class,
    }
    mutation_fields[update_field_name] = strawberry.mutation(update_resolver)

    # ---- Dynamically build the class ----
    MutationClass = type("Mutation", (object,), mutation_fields)
    return strawberry.type(MutationClass, name="Mutation")
