"""
Reusable module to build nested Pydantic models dynamically
from a list of schema fields (endpoints in the schema tree).

This module supports building Pydantic models at runtime based on a schema definition,
allowing flexible data validation for various use cases (e.g., query filters, mutations, or full models).
All fields in generated models are Optional and default to None.

Functions:
    build_dynamic_model: Creates nested Pydantic models from schema fields.
    build_dynamic_models: Loads schema fields and builds all model variants (filters, mutations, full model).
"""

import logging
import os
import re
from datetime import date, datetime
from enum import Enum
from typing import Annotated, Any, Dict, List, Optional, Tuple, Type, TypeVar, cast

from pydantic import BaseModel, ConfigDict, Field

from lif.datatypes.schema import SchemaField
from lif.schema.core import load_schema_nodes
from lif.string_utils.core import to_pascal_case


# ===== Environment and Global Config =====

ROOT_NODE: str | None = os.getenv("ROOT_NODE")
OPENAPI_SCHEMA_FILE: str | None = os.getenv("OPENAPI_SCHEMA_FILE")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

T = TypeVar("T")
ModelDict = Dict[str, Type[BaseModel]]

#: Map XML-Schema datatypes ➜ native Python types
DATATYPE_MAP: dict[str, type[Any]] = {
    "xsd:string": str,
    "xsd:decimal": float,
    "xsd:integer": int,
    "xsd:boolean": bool,
    "xsd:date": date,
    "xsd:dateTime": datetime,
    "xsd:datetime": datetime,
    "xsd:anyURI": str,
}

#: Singleton cache to prevent duplicate Enum definitions
_ENUM_CLASS_CACHE: Dict[str, Type[Enum]] = {}

_TRUTHY = {"yes", "true", "1"}


# ===== Helpers =====


def _is_yes(value: Any) -> bool:
    """Check if value is a truthy 'yes' string."""
    return str(value).strip().lower() in _TRUTHY


def _to_enum_member(label: str) -> str:
    """Convert a string label into a valid Enum member name."""
    key = re.sub(r"\W|^(?=\d)", "_", label.upper())
    return key


def make_enum(name: str, values: List[Any]) -> Type[Enum]:
    """Return a cached Enum type for the given values."""
    cache_key = f"{name}_{'_'.join(map(str, sorted(values)))}"
    if cache_key in _ENUM_CLASS_CACHE:  # short-circuit hit
        return _ENUM_CLASS_CACHE[cache_key]

    # Ensure value type is compatible with typing stubs and tooling
    members: Dict[str, object] = {_to_enum_member(v): v for v in values}
    # Use functional API with explicit module for better pickling/introspection
    enum_cls = cast(Type[Enum], Enum(name, members, module=__name__))
    # enum_cls = type(name, (Enum,), {"__module__": __name__, **members})  # alternative
    _ENUM_CLASS_CACHE[cache_key] = enum_cls
    return enum_cls


# ===== Core builders =====


def build_dynamic_model(
    schema_fields: List[SchemaField],
    *,
    attribute_flag: str | None = "xQueryable",
    model_doc: str = "Data model",
    allow_extra: bool = False,
    model_suffix: str = "",
    all_optional: bool = True,
) -> ModelDict:
    """Create nested Pydantic models for the given schema fields.

    Args:
        schema_fields (List[SchemaField]): Leaf-level schema nodes.
        attribute_flag (str | None): Only include fields whose attributes[flag] is truthy.
            Use None to include all fields.
        model_doc (str): Base docstring used for generated classes.
        allow_extra (bool): If True, allows extra properties (additionalProperties: true).
        model_suffix (str): Suffix for model class names (e.g., "Type", "Filter", "Mutation").
        all_optional (bool): If True, all fields will be Optional and default to None.

    Returns:
        ModelDict: A mapping { model_name: Pydantic class }.
    """

    # Build a *tree* structure and a quick lookup for leaf nodes.
    tree: dict[str, Any] = {}
    leaf_by_path: Dict[Tuple[str, ...], SchemaField] = {}

    for sf in schema_fields:
        if attribute_flag and not sf.attributes.get(attribute_flag, False):
            continue

        parts = sf.json_path.split(".")
        node = tree
        for i, part in enumerate(parts):
            node = node.setdefault(part, {})
            if i == len(parts) - 1:
                leaf_by_path[tuple(parts)] = sf

    if not tree:
        return {}

    if len(tree) != 1:
        raise ValueError(f"All {attribute_flag or 'selected'} json_path values must share a common root")

    # ===== Internal utilities =====

    def _field_type(sf: SchemaField, name: str) -> Any:
        """Translate a SchemaField to a typing type.

        Args:
            sf (SchemaField): The schema field.
            name (str): Name for enum classes.

        Returns:
            Any: The Python type or Enum for the field.
        """
        if "enum" in sf.attributes:
            base: Any = make_enum(name.capitalize(), sf.attributes["enum"])
        else:
            base = DATATYPE_MAP.get(sf.attributes.get("dataType", "xsd:string"), str)

        if _is_yes(sf.attributes.get("array", "No")):
            base = List[base]

        if all_optional:
            return Optional[base]
        return base

    def _wrap_root(root_name: str, inner: Type[BaseModel], is_array: bool) -> Type[BaseModel]:
        """Create a top-level Pydantic wrapper model with the specified root name.

        Args:
            root_name (str): Root field name.
            inner (Type[BaseModel]): The inner model class.
            is_array (bool): If True, wraps the model in a List[].

        Returns:
            Type[BaseModel]: The generated wrapper model.
        """
        field_type: Any = List[inner] if is_array else inner
        annotations = {root_name: field_type}
        doc = f"Top-level wrapper with `{root_name}` field." if root_name else "Top-level wrapper."
        class_name = f"{root_name.capitalize()}{model_suffix}"
        namespace = {
            "__annotations__": annotations,
            "__doc__": doc,
            "model_config": ConfigDict(strict=False, extra="allow" if allow_extra else "forbid"),
        }
        # Only set default if all_optional
        if all_optional:
            namespace[root_name] = None
        return type(class_name, (BaseModel,), namespace)

    # ===== Recursive Model Builder =====

    models: ModelDict = {}

    def strip_root(parts):
        """Remove the root node from the path."""
        if parts and parts[0].lower() == root_name.lower():
            return parts[1:]
        return parts

    def _build_model(name: str, subtree: dict[str, Any], path: Tuple[str, ...]) -> Type[BaseModel] | None:
        """Recursively build nested Pydantic models.

        Args:
            name (str): Model class name.
            subtree (dict[str, Any]): Subtree of the schema.
            path (Tuple[str, ...]): Current path in the tree.

        Returns:
            Type[BaseModel] | None: The constructed model or None if no fields.
        """
        sf = leaf_by_path.get(path)
        stripped = strip_root(path)
        if stripped:
            class_name = to_pascal_case("".join(x for x in stripped))
        else:
            class_name = to_pascal_case(root_name)
        if model_suffix and not class_name.endswith(model_suffix):
            class_name = f"{class_name}{model_suffix}"
        # Guarantee non-empty unique_name for root
        unique_name = (sf.attributes.get("uniqueName") if sf else None) or ".".join(stripped) or class_name

        annotations: Dict[str, Any] = {}
        defaults: Dict[str, Any] = {}

        for key, child in subtree.items():
            child_path = path + (key,)
            leaf_sf = leaf_by_path.get(child_path)

            if not child:  # leaf
                if leaf_sf:
                    if all_optional:
                        annotations[key] = Annotated[
                            Optional[_field_type(leaf_sf, to_pascal_case(key))], Field(description=leaf_sf.description)
                        ]
                        defaults[key] = None
                    else:
                        annotations[key] = Annotated[
                            _field_type(leaf_sf, to_pascal_case(key)), Field(description=leaf_sf.description)
                        ]
                        # No default: required
            else:  # branch ➜ nested model
                is_array = _is_yes(leaf_sf.attributes.get("array", "No")) if leaf_sf else False
                child_model = _build_model(key.capitalize(), child, child_path)
                if child_model:
                    if all_optional:
                        annotations[key] = Optional[List[child_model]] if is_array else Optional[child_model]
                        defaults[key] = None
                    else:
                        annotations[key] = List[child_model] if is_array else child_model
                        # No default: required

        if not annotations:
            return None

        desc = f"{model_doc} for `{class_name}`."
        namespace = {
            "__annotations__": annotations,
            "__doc__": desc,
            "__module__": __name__,
            # Use supported ConfigDict keys; attach metadata via json_schema_extra
            "model_config": ConfigDict(
                # TODO (from before integration into this repo): Make sure the change from this works: title=class_name, description=desc, strict=False, extra="allow" if allow_extra else "forbid"
                title=class_name,
                strict=False,
                extra="allow" if allow_extra else "forbid",
                json_schema_extra={"description": desc},
            ),
        }
        # Only set defaults for all_optional
        if all_optional:
            namespace.update(defaults)
        cls = type(class_name, (BaseModel,), namespace)
        models[unique_name] = cls
        return cls

    # ===== Build Root + Wrapper =====

    # TODO (from before integration into this repo): This forces the wrapper structure. It should use OpenAPI schema

    root_name = next(iter(tree))

    inner_model = _build_model(root_name.capitalize(), tree[root_name], (root_name,))
    if inner_model is None:  # pragma: no cover – safeguard
        return {}

    # Just force as array:
    wrapper_model = _wrap_root(root_name, inner_model, True)

    models[root_name] = inner_model
    models[f"{root_name}_wrapper"] = wrapper_model
    return models


# ===== External Entrypoints =====


def get_schema_fields() -> List[SchemaField]:
    """
    Load and return the list of schema fields from the configured schema source.

    Returns:
        List[SchemaField]: The schema fields for the root node.
    """
    # Read environment at call time to allow tests/runtime overrides
    openapi_file = os.getenv("OPENAPI_SCHEMA_FILE", OPENAPI_SCHEMA_FILE)
    root_node = os.getenv("ROOT_NODE", ROOT_NODE)
    if openapi_file is None:
        raise ValueError("OPENAPI_SCHEMA_FILE environment variable is not set")
    return load_schema_nodes(openapi_file, root_node)


def build_filter_models(fields: List[SchemaField], *, allow_extra: bool = True, all_optional: bool = True) -> ModelDict:
    """
    Build filter models from schema fields.

    Args:
        fields (List[SchemaField]): Schema fields.
        allow_extra (bool, optional): Allow extra properties in models. Default is True.
        all_optional (bool, optional): Make all fields Optional and default to None. Default is True.

    Returns:
        ModelDict: A mapping { model_name: Pydantic class } for filter models.
    """
    return build_dynamic_model(
        fields,
        attribute_flag="xQueryable",
        model_doc="Filter data model",
        model_suffix="Filter",
        allow_extra=allow_extra,
        all_optional=all_optional,
    )


def build_mutation_models(
    fields: List[SchemaField], *, allow_extra: bool = False, all_optional: bool = True
) -> ModelDict:
    """
    Build mutation models from schema fields.

    Args:
        fields (List[SchemaField]): Schema fields.
        allow_extra (bool, optional): Allow extra properties in models. Default is False.
        all_optional (bool, optional): Make all fields Optional and default to None. Default is True.

    Returns:
        ModelDict: A mapping { model_name: Pydantic class } for mutation models.
    """
    return build_dynamic_model(
        fields,
        attribute_flag="xMutable",
        model_doc="Mutation data model",
        model_suffix="Mutation",
        allow_extra=allow_extra,
        all_optional=all_optional,
    )


def build_full_models(fields: List[SchemaField], *, allow_extra: bool = False, all_optional: bool = False) -> ModelDict:
    """
    Build full (strict) models from schema fields.

    Args:
        fields (List[SchemaField]): Schema fields.
        allow_extra (bool, optional): Allow extra properties in models. Default is False.
        all_optional (bool, optional): Make all fields Optional and default to None. Default is False (fields required).

    Returns:
        ModelDict: A mapping { model_name: Pydantic class } for full models.
    """
    return build_dynamic_model(
        fields,
        attribute_flag=None,
        model_doc="Full data model",
        model_suffix="Type",
        allow_extra=allow_extra,
        all_optional=all_optional,
    )


def build_all_models(
    *,
    filter_allow_extra: bool = True,
    filter_all_optional: bool = True,
    mutation_allow_extra: bool = False,
    mutation_all_optional: bool = True,
    full_allow_extra: bool = False,
    full_all_optional: bool = False,
) -> tuple[List[SchemaField], ModelDict, ModelDict, ModelDict]:
    """
    Build all three model sets (filter, mutation, full) in one go, optionally customizing allow_extra and all_optional for each.

    Keyword Args:
        filter_allow_extra (bool): Allow extra properties in filter models. Default True.
        filter_all_optional (bool): Make all filter model fields Optional. Default True.
        mutation_allow_extra (bool): Allow extra properties in mutation models. Default False.
        mutation_all_optional (bool): Make all mutation model fields Optional. Default True.
        full_allow_extra (bool): Allow extra properties in full models. Default False.
        full_all_optional (bool): Make all full model fields Optional. Default False (fields required).

    Returns:
        tuple:
            - List[SchemaField]: Schema fields.
            - ModelDict: Filter models.
            - ModelDict: Mutation models.
            - ModelDict: Full models.
    """
    fields = get_schema_fields()
    return (
        fields,
        build_filter_models(fields, allow_extra=filter_allow_extra, all_optional=filter_all_optional),
        build_mutation_models(fields, allow_extra=mutation_allow_extra, all_optional=mutation_all_optional),
        build_full_models(fields, allow_extra=full_allow_extra, all_optional=full_all_optional),
    )
