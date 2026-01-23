"""Tests for LIF schema configuration component."""

import os
import pytest
from unittest.mock import patch

from lif.lif_schema_config import (
    LIFSchemaConfig,
    LIFSchemaConfigError,
    # Naming functions
    to_graphql_query_name,
    to_schema_name,
    to_mutation_name,
    to_camel_case,
    to_pascal_case,
    to_snake_case,
    safe_identifier,
    normalize_identifier_type,
    # Type mappings
    XSD_TO_PYTHON,
    python_type_for_xsd,
    xsd_type_for_python,
    # OpenAPI helpers
    get_schemas,
    is_queryable,
    is_mutable,
    get_field_description,
    OpenAPIExtensions,
)
from datetime import date, datetime


# =============================================================================
# LIFSchemaConfig Tests
# =============================================================================

class TestLIFSchemaConfig:
    """Tests for the main configuration class."""

    def test_default_config(self):
        """Test that default configuration is valid."""
        config = LIFSchemaConfig()
        assert config.root_type_name == "Person"
        assert "Course" in config.additional_root_types
        assert "Course" in config.reference_data_roots
        assert config.query_timeout_seconds == 20

    def test_computed_properties(self):
        """Test computed properties."""
        config = LIFSchemaConfig()
        assert config.graphql_query_name == "person"
        assert config.mutation_name == "updatePerson"
        assert config.query_planner_query_url == "http://localhost:8002/query"
        assert config.query_planner_update_url == "http://localhost:8002/update"
        assert "Person" in config.all_root_types

    def test_validation_root_in_reference(self):
        """Test validation fails if root_type_name in reference_data_roots."""
        with pytest.raises(LIFSchemaConfigError) as exc_info:
            LIFSchemaConfig(
                root_type_name="Person",
                reference_data_roots={"Person", "Course"},
            )
        assert "should not be in reference_data_roots" in str(exc_info.value)

    def test_validation_invalid_reference_root(self):
        """Test validation fails if reference root not in all roots."""
        with pytest.raises(LIFSchemaConfigError) as exc_info:
            LIFSchemaConfig(
                root_type_name="Person",
                additional_root_types=["Course"],
                reference_data_roots={"Course", "InvalidRoot"},
            )
        assert "must be in root types" in str(exc_info.value)

    def test_from_environment(self):
        """Test loading configuration from environment variables."""
        env_vars = {
            "LIF_GRAPHQL_ROOT_TYPE_NAME": "TestEntity",
            "LIF_GRAPHQL_ROOT_NODES": "RefA,RefB",
            "LIF_GRAPHQL_REFERENCE_DATA_ROOTS": "RefA,RefB",
            "LIF_QUERY_PLANNER_URL": "http://test:9000",
            "SEMANTIC_SEARCH__TOP_K": "50",
        }
        with patch.dict(os.environ, env_vars, clear=False):
            config = LIFSchemaConfig.from_environment()
            assert config.root_type_name == "TestEntity"
            assert config.additional_root_types == ["RefA", "RefB"]
            assert config.reference_data_roots == {"RefA", "RefB"}
            assert config.query_planner_base_url == "http://test:9000"
            assert config.semantic_search_top_k == 50

    def test_is_reference_data_root(self):
        """Test checking if a root is reference data."""
        config = LIFSchemaConfig()
        assert config.is_reference_data_root("Course") is True
        assert config.is_reference_data_root("Person") is False

    def test_get_queryable_roots(self):
        """Test getting queryable (non-reference) roots."""
        config = LIFSchemaConfig(
            root_type_name="Person",
            additional_root_types=["Course", "Organization"],
            reference_data_roots={"Course", "Organization"},
        )
        queryable = config.get_queryable_roots()
        assert queryable == ["Person"]


# =============================================================================
# Naming Convention Tests
# =============================================================================

class TestNamingConventions:
    """Tests for naming convention functions."""

    def test_to_graphql_query_name(self):
        assert to_graphql_query_name("Person") == "person"
        assert to_graphql_query_name("CourseLearningExperience") == "courseLearningExperience"
        assert to_graphql_query_name("") == ""

    def test_to_schema_name(self):
        assert to_schema_name("person") == "Person"
        assert to_schema_name("courseLearningExperience") == "CourseLearningExperience"
        assert to_schema_name("") == ""

    def test_to_mutation_name(self):
        assert to_mutation_name("Person", "update") == "updatePerson"
        assert to_mutation_name("Course", "create") == "createCourse"
        assert to_mutation_name("Organization", "delete") == "deleteOrganization"

    def test_to_camel_case(self):
        assert to_camel_case("hello_world") == "helloWorld"
        assert to_camel_case("hello-world") == "helloWorld"
        assert to_camel_case("HelloWorld") == "helloWorld"

    def test_to_pascal_case(self):
        assert to_pascal_case("person", "identifier", "enum") == "PersonIdentifierEnum"
        assert to_pascal_case("course") == "Course"

    def test_to_snake_case(self):
        assert to_snake_case("PersonIdentifier") == "person_identifier"
        assert to_snake_case("personIdentifier") == "person_identifier"

    def test_safe_identifier(self):
        assert safe_identifier("x-queryable") == "x_queryable"
        assert safe_identifier("123field") == "_123field"
        assert safe_identifier("valid_name") == "valid_name"

    def test_normalize_identifier_type(self):
        assert normalize_identifier_type("School-assigned number") == "SCHOOL_ASSIGNED_NUMBER"
        assert normalize_identifier_type("INSTITUTION_ASSIGNED_NUMBER") == "INSTITUTION_ASSIGNED_NUMBER"


# =============================================================================
# Type Mapping Tests
# =============================================================================

class TestTypeMappings:
    """Tests for XSD type mappings."""

    def test_xsd_to_python_mappings(self):
        assert XSD_TO_PYTHON["xsd:string"] == str
        assert XSD_TO_PYTHON["xsd:integer"] == int
        assert XSD_TO_PYTHON["xsd:boolean"] == bool
        assert XSD_TO_PYTHON["xsd:date"] == date
        assert XSD_TO_PYTHON["xsd:dateTime"] == datetime

    def test_python_type_for_xsd(self):
        assert python_type_for_xsd("xsd:string") == str
        assert python_type_for_xsd("xsd:integer") == int
        assert python_type_for_xsd("unknown_type") == str  # default
        assert python_type_for_xsd("unknown_type", default=int) == int

    def test_xsd_type_for_python(self):
        assert xsd_type_for_python(str) == "xsd:string"
        assert xsd_type_for_python(int) == "xsd:integer"
        assert xsd_type_for_python(list) == "xsd:string"  # default


# =============================================================================
# OpenAPI Helper Tests
# =============================================================================

class TestOpenAPIHelpers:
    """Tests for OpenAPI document helpers."""

    def test_get_schemas_openapi3(self):
        """Test extracting schemas from OpenAPI 3.x document."""
        doc = {
            "components": {
                "schemas": {
                    "Person": {"type": "object"},
                    "Course": {"type": "object"},
                }
            }
        }
        schemas = get_schemas(doc)
        assert "Person" in schemas
        assert "Course" in schemas

    def test_get_schemas_swagger2(self):
        """Test extracting schemas from Swagger 2.x document."""
        doc = {
            "definitions": {
                "Person": {"type": "object"},
            }
        }
        schemas = get_schemas(doc)
        assert "Person" in schemas

    def test_get_schemas_not_found(self):
        """Test error when no schemas found."""
        with pytest.raises(ValueError) as exc_info:
            get_schemas({})
        assert "No schemas found" in str(exc_info.value)

    def test_is_queryable(self):
        """Test queryable field detection."""
        assert is_queryable({"x-queryable": True}) is True
        assert is_queryable({"x-queryable": False}) is False
        assert is_queryable({}) is False

    def test_is_queryable_nested(self):
        """Test queryable detection in nested objects."""
        field_def = {
            "type": "object",
            "properties": {
                "id": {"x-queryable": True},
            }
        }
        assert is_queryable(field_def) is True

    def test_is_mutable(self):
        """Test mutable field detection."""
        assert is_mutable({"x-mutable": True}) is True
        assert is_mutable({"x-mutable": False}) is False
        assert is_mutable({}) is False

    def test_get_field_description(self):
        """Test extracting field descriptions."""
        # PascalCase (old schema)
        assert get_field_description({"Description": "Test desc"}) == "Test desc"
        # lowercase (new schema)
        assert get_field_description({"description": "Test desc"}) == "Test desc"
        # No description
        assert get_field_description({}) is None
        # Description is an object (old schema edge case)
        assert get_field_description({"description": {"nested": "object"}}) is None

    def test_openapi_extensions_constants(self):
        """Test OpenAPI extension constants are defined."""
        assert OpenAPIExtensions.QUERYABLE == "x-queryable"
        assert OpenAPIExtensions.MUTABLE == "x-mutable"
        assert OpenAPIExtensions.DATA_TYPE == "DataType"
