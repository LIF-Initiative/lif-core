"""Tests for openapi_to_graphql type_factory and core module."""

import json
from pathlib import Path
from typing import List, Optional

import strawberry

from lif.openapi_to_graphql.core import generate_graphql_schema
from lif.openapi_to_graphql.type_factory import (
    build_root_mutation_type,
    build_root_query_type,
    create_enum_type,
    create_type,
)


# === Helpers ===


def _empty_openapi(schemas: dict) -> dict:
    """Wrap schemas dict in a minimal OpenAPI structure."""
    return {"components": {"schemas": schemas}}


def _make_scalar_field(data_type="xsd:string", queryable=False, mutable=False, **extra):
    field = {"DataType": data_type, "Array": "No", "x-queryable": queryable, "x-mutable": mutable}
    field.update(extra)
    return field


def _is_strawberry_type(cls):
    """Check if a class was decorated by strawberry.type."""
    return hasattr(cls, "__strawberry_definition__") or hasattr(cls, "_type_definition")


# === Test: create_type — basic object type ===


class TestCreateTypeBasicObject:
    def test_returns_strawberry_type_with_scalar_properties(self):
        schema = {
            "type": "object",
            "properties": {
                "firstName": _make_scalar_field(),
                "age": _make_scalar_field("xsd:integer"),
            },
        }
        openapi = _empty_openapi({})
        created_types = {}
        queryable_fields = {}

        result = create_type("BasicPerson", schema, openapi, created_types, queryable_fields)

        assert _is_strawberry_type(result), f"Expected Strawberry type, got {result}"
        assert "BasicPerson" in created_types
        assert hasattr(result, "__strawberry_definition__") or hasattr(result, "_type_definition")

    def test_required_vs_optional_annotations(self):
        schema = {
            "type": "object",
            "required": ["firstName"],
            "properties": {
                "firstName": _make_scalar_field(),
                "lastName": _make_scalar_field(),
            },
        }
        created_types = {}

        result = create_type("ReqTest", schema, _empty_openapi({}), created_types, {})

        annotations = result.__annotations__
        # Required field should NOT be Optional
        assert annotations["first_name"] is str or annotations["first_name"] == str
        # Optional field SHOULD be Optional
        last_name_ann = annotations["last_name"]
        assert last_name_ann == Optional[str]


# === Test: create_type — recursive/self-referencing $ref ===


class TestCreateTypeRecursiveRef:
    def test_self_referencing_type_is_strawberry_type(self):
        """Schema where type A has a property that $refs back to A.

        This is the exact pattern that caused the crash-loop bug — the placeholder
        `object` subclass was returned from cache instead of the final Strawberry type.
        """
        schemas = {
            "TreeNode": {
                "type": "object",
                "properties": {
                    "name": _make_scalar_field(),
                    "child": {"$ref": "#/components/schemas/TreeNode"},
                },
            }
        }
        openapi = _empty_openapi(schemas)
        created_types = {}

        result = create_type("TreeNode", schemas["TreeNode"], openapi, created_types, {})

        assert _is_strawberry_type(result), (
            f"Self-referencing type should be a Strawberry type, got {result} "
            f"(bases: {getattr(result, '__bases__', 'N/A')})"
        )
        # The cached version must also be the final Strawberry type, not the placeholder
        assert _is_strawberry_type(created_types["TreeNode"])


# === Test: create_type — mutual $ref (A → B → A) ===


class TestCreateTypeMutualRef:
    def test_mutually_referencing_types_are_strawberry_types(self):
        schemas = {
            "Department": {
                "type": "object",
                "properties": {
                    "name": _make_scalar_field(),
                    "manager": {"$ref": "#/components/schemas/Employee"},
                },
            },
            "Employee": {
                "type": "object",
                "properties": {
                    "name": _make_scalar_field(),
                    "department": {"$ref": "#/components/schemas/Department"},
                },
            },
        }
        openapi = _empty_openapi(schemas)
        created_types = {}

        dept_type = create_type("Department", schemas["Department"], openapi, created_types, {})
        emp_type = create_type("Employee", schemas["Employee"], openapi, created_types, {})

        assert _is_strawberry_type(dept_type), f"Department should be Strawberry type, got {dept_type}"
        assert _is_strawberry_type(emp_type), f"Employee should be Strawberry type, got {emp_type}"
        assert _is_strawberry_type(created_types["Department"])
        assert _is_strawberry_type(created_types["Employee"])


# === Test: create_type — object with no properties ===


class TestCreateTypeEmptyProperties:
    def test_returns_str_fallback(self):
        schema = {"type": "object", "properties": {}}
        created_types = {}

        result = create_type("EmptyObj", schema, _empty_openapi({}), created_types, {})

        assert result is str


# === Test: create_type — array with nested object ===


class TestCreateTypeArrayWithObject:
    def test_returns_list_of_strawberry_type(self):
        schema = {
            "type": "array",
            "properties": {
                "value": _make_scalar_field(),
            },
        }
        created_types = {}

        result = create_type("Scores", schema, _empty_openapi({}), created_types, {})

        # Should be List[ScoresItem]
        assert hasattr(result, "__origin__") or str(result).startswith("typing.List")
        # The item type should be a Strawberry type
        item_type = result.__args__[0]
        assert _is_strawberry_type(item_type), f"Item type should be Strawberry type, got {item_type}"


# === Test: create_type — enum field ===


class TestCreateTypeWithEnum:
    def test_creates_enum_for_enum_field(self):
        schema = {
            "type": "object",
            "properties": {
                "status": {
                    "enum": ["ACTIVE", "INACTIVE", "PENDING"],
                    "x-queryable": True,
                },
            },
        }
        created_types = {}

        result = create_type("Account", schema, _empty_openapi({}), created_types, {})

        assert _is_strawberry_type(result)
        # The enum type should have been created in created_types
        enum_type_found = any("Enum" in key for key in created_types if key != "Account")
        assert enum_type_found, f"Expected enum in created_types, got keys: {list(created_types.keys())}"


# === Test: create_enum_type directly ===


class TestCreateEnumType:
    def test_creates_strawberry_enum(self):
        created_types = {}
        result = create_enum_type("ColorEnum", ["RED", "GREEN", "BLUE"], created_types)

        assert "ColorEnum" in created_types
        # Should be usable as an enum
        assert hasattr(result, "RED") or hasattr(result, "__members__")

    def test_caches_enum(self):
        created_types = {}
        first = create_enum_type("CachedEnum", ["A", "B"], created_types)
        second = create_enum_type("CachedEnum", ["A", "B"], created_types)
        assert first is second


# === Test: generate_graphql_schema — end-to-end with bundled file ===


class TestGenerateGraphqlSchemaEndToEnd:
    async def test_bundled_schema_produces_valid_strawberry_schema(self):
        """Load the bundled OpenAPI schema and verify it generates a valid Strawberry Schema.

        This catches regressions from schema content changes and recursive $ref issues.
        """
        schema_path = Path(__file__).resolve().parents[4] / (
            "components/lif/mdr_client/resources/openapi_constrained_with_interactions.json"
        )
        with open(schema_path) as f:
            openapi = json.load(f)

        schema = await generate_graphql_schema(
            openapi=openapi,
            root_type_name="Person",
            query_planner_query_url="http://localhost:9999/query",
            query_planner_update_url="http://localhost:9999/update",
        )

        assert isinstance(schema, strawberry.Schema)

        # Introspection should not raise
        introspection_query = """
        {
            __schema {
                queryType { name }
                mutationType { name }
            }
        }
        """
        result = await schema.execute(introspection_query)
        assert result.errors is None or len(result.errors) == 0, f"Introspection errors: {result.errors}"
        assert result.data["__schema"]["queryType"]["name"] == "Query"


# === Test: build_root_mutation_type — with None filter/input ===


class TestBuildRootMutationTypeNoneInputs:
    def test_builds_mutation_when_mutable_input_missing(self):
        """When mutable_input_types doesn't have the root type, mutation should still build."""
        # First create a minimal type to use as root
        schema = {
            "type": "object",
            "properties": {
                "name": _make_scalar_field(),
            },
        }
        created_types = {}
        create_type("Thing", schema, _empty_openapi({}), created_types, {})

        # Both mutable_input_types and input_types lack "Thing"
        mutation_type = build_root_mutation_type(
            root_name="Thing",
            created_types=created_types,
            query_planner_update_url="http://localhost:9999/update",
            mutable_input_types={},
            input_types={},
        )

        assert _is_strawberry_type(mutation_type)

    def test_builds_mutation_with_none_input_types_arg(self):
        """When input_types is passed as None."""
        schema = {
            "type": "object",
            "properties": {
                "name": _make_scalar_field(),
            },
        }
        created_types = {}
        create_type("Widget", schema, _empty_openapi({}), created_types, {})

        mutation_type = build_root_mutation_type(
            root_name="Widget",
            created_types=created_types,
            query_planner_update_url="http://localhost:9999/update",
            mutable_input_types={},
            input_types=None,
        )

        assert _is_strawberry_type(mutation_type)


# === Test: build_root_query_type — with and without filter ===


class TestBuildRootQueryType:
    def test_builds_query_without_filter(self):
        schema = {
            "type": "object",
            "properties": {
                "name": _make_scalar_field(),
            },
        }
        created_types = {}
        create_type("Item", schema, _empty_openapi({}), created_types, {})

        query_type = build_root_query_type(
            root_name="Item",
            created_types=created_types,
            query_planner_query_url="http://localhost:9999/query",
            input_types={},
        )

        assert _is_strawberry_type(query_type)


# === Canary: strawberry.type() must decorate in-place ===


class TestStrawberryTypeDecoratesInPlace:
    """Canary test that verifies strawberry.type() modifies the class in-place.

    The $ref handling in create_type() relies on this: a placeholder is cached
    before decoration, and recursive references return that cached placeholder.
    If strawberry.type() ever starts returning a *different* object, those
    recursive references would hold a bare object subclass, causing
    TypeError: Unexpected type '<class 'object'>' during Schema construction.

    If this test fails after a Strawberry upgrade, create_type() must be
    reworked to use lazy type references (e.g., strawberry.lazy) instead of
    the placeholder cache pattern.
    """

    def test_strawberry_type_returns_same_object(self):
        cls = type("Canary", (object,), {})
        cls.__annotations__ = {"name": str}
        cls.name = strawberry.field(name="name")

        decorated = strawberry.type(cls)

        assert decorated is cls, (
            "strawberry.type() returned a different object than the input class. "
            "This breaks the placeholder-cache pattern in create_type() for recursive $ref schemas. "
            f"Input id={id(cls)}, output id={id(decorated)}"
        )
