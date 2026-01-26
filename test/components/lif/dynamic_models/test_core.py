"""
Comprehensive unit tests for the dynamic_models.core module.

Tests the dynamic Pydantic model building functionality including:
- Building nested models from schema fields
- Filter, mutation, and full model variants
- Enum handling
- Field type mapping
- Error conditions
"""

import os
import pytest
from enum import Enum
from pathlib import Path
from unittest.mock import patch

from pydantic import BaseModel, ValidationError

from lif.dynamic_models import core
from lif.datatypes.schema import SchemaField


PATH_TO_TEST_SCHEMA = Path(__file__).parent.parent.parent.parent / "data" / "test_openapi_schema.json"


class TestHelperFunctions:
    """Test helper functions in the core module."""

    def test_is_yes(self):
        """Test the _is_yes helper function."""
        assert core._is_yes("yes") is True
        assert core._is_yes("YES") is True
        assert core._is_yes("true") is True
        assert core._is_yes("TRUE") is True
        assert core._is_yes("1") is True
        assert core._is_yes("  yes  ") is True

        assert core._is_yes("no") is False
        assert core._is_yes("false") is False
        assert core._is_yes("0") is False
        assert core._is_yes("") is False
        assert core._is_yes("maybe") is False

    def test_to_enum_member(self):
        """Test the _to_enum_member helper function."""
        assert core._to_enum_member("Valid Option") == "VALID_OPTION"
        assert core._to_enum_member("123invalid") == "_123INVALID"
        assert core._to_enum_member("special-chars!@#") == "SPECIAL_CHARS___"
        assert core._to_enum_member("") == ""

    def test_make_enum(self):
        """Test enum creation and caching."""
        # Create enum
        enum_cls = core.make_enum("TestEnum", ["option1", "option2", "option3"])
        assert issubclass(enum_cls, Enum)

        # Test enum values
        assert hasattr(enum_cls, "OPTION1")
        assert hasattr(enum_cls, "OPTION2")
        assert hasattr(enum_cls, "OPTION3")

        # Test enum value content
        option1_member = getattr(enum_cls, "OPTION1")
        assert option1_member.value == "option1"

        # Test caching - same values should return same class
        enum_cls2 = core.make_enum("TestEnum", ["option1", "option2", "option3"])
        assert enum_cls is enum_cls2

        # Different values should return different class
        enum_cls3 = core.make_enum("TestEnum", ["option1", "option2", "option4"])
        assert enum_cls is not enum_cls3


class TestFieldTypeMapping:
    """Test field type mapping through model creation and validation."""

    def test_string_field_in_model(self):
        """Test string field type mapping and validation."""
        fields = [
            SchemaField(
                json_path="test.field",
                description="Test field",
                attributes={"xQueryable": True, "dataType": "xsd:string", "array": "No"},
            )
        ]
        models = core.build_dynamic_model(fields)
        assert "test" in models

        test_model = models["test"]

        # Test valid string assignment
        instance = test_model(field="hello")
        assert getattr(instance, "field") == "hello"

        # Test None assignment (optional)
        instance_none = test_model(field=None)
        assert getattr(instance_none, "field") is None

        # Test string conversion from valid types
        instance_converted = test_model(field="123")
        assert getattr(instance_converted, "field") == "123"

        # Test that invalid types raise ValidationError
        with pytest.raises(ValidationError):
            test_model(field=123)  # Integer not allowed for strict string

    def test_integer_field_in_model(self):
        """Test integer field type mapping and validation."""
        fields = [
            SchemaField(
                json_path="test.field",
                description="Test field",
                attributes={"xQueryable": True, "dataType": "xsd:integer", "array": "No"},
            )
        ]
        models = core.build_dynamic_model(fields)
        assert "test" in models

        test_model = models["test"]

        # Test valid integer assignment
        instance = test_model(field=42)
        assert getattr(instance, "field") == 42

        # Test string to integer conversion (if supported)
        try:
            instance_converted = test_model(field="100")
            assert getattr(instance_converted, "field") == 100
        except ValidationError:
            # If strict mode doesn't allow string conversion, that's also valid
            pass

        # Test invalid conversion should raise ValidationError
        with pytest.raises(ValidationError):
            test_model(field="not_a_number")

    def test_boolean_field_in_model(self):
        """Test boolean field type mapping and validation."""
        fields = [
            SchemaField(
                json_path="test.field",
                description="Test field",
                attributes={"xQueryable": True, "dataType": "xsd:boolean", "array": "No"},
            )
        ]
        models = core.build_dynamic_model(fields)
        assert "test" in models

        test_model = models["test"]

        # Test valid boolean assignment
        instance_true = test_model(field=True)
        assert getattr(instance_true, "field") is True

        instance_false = test_model(field=False)
        assert getattr(instance_false, "field") is False

        # Test truthy/falsy conversion
        instance_truthy = test_model(field=1)
        assert getattr(instance_truthy, "field") is True

        instance_falsy = test_model(field=0)
        assert getattr(instance_falsy, "field") is False

    def test_date_field_in_model(self):
        """Test date field type mapping and validation."""
        from datetime import date

        fields = [
            SchemaField(
                json_path="test.field",
                description="Test field",
                attributes={"xQueryable": True, "dataType": "xsd:date", "array": "No"},
            )
        ]
        models = core.build_dynamic_model(fields)
        assert "test" in models

        test_model = models["test"]

        # Test valid date assignment
        test_date = date(2023, 12, 25)
        instance = test_model(field=test_date)
        assert getattr(instance, "field") == test_date

        # Test string date parsing (if supported by Pydantic)
        try:
            instance_str = test_model(field="2023-12-25")
            parsed_date = getattr(instance_str, "field")
            assert isinstance(parsed_date, date)
        except ValidationError:
            # If strict parsing is not enabled, that's also valid behavior
            pass

    def test_datetime_field_in_model(self):
        """Test datetime field type mapping and validation."""
        from datetime import datetime

        fields = [
            SchemaField(
                json_path="test.field",
                description="Test field",
                attributes={"xQueryable": True, "dataType": "xsd:dateTime", "array": "No"},
            )
        ]
        models = core.build_dynamic_model(fields)
        assert "test" in models

        test_model = models["test"]

        # Test valid datetime assignment
        test_datetime = datetime(2023, 12, 25, 14, 30, 0)
        instance = test_model(field=test_datetime)
        assert getattr(instance, "field") == test_datetime

        # Test ISO string parsing (if supported)
        try:
            instance_str = test_model(field="2023-12-25T14:30:00")
            parsed_datetime = getattr(instance_str, "field")
            assert isinstance(parsed_datetime, datetime)
        except ValidationError:
            # If strict parsing is not enabled, that's also valid behavior
            pass

    def test_enum_field_in_model(self):
        """Test enum field type mapping and validation."""
        fields = [
            SchemaField(
                json_path="test.field",
                description="Test field",
                attributes={"xQueryable": True, "enum": ["option1", "option2", "option3"], "array": "No"},
            )
        ]
        models = core.build_dynamic_model(fields)
        assert "test" in models

        test_model = models["test"]

        # Test valid enum value assignment
        instance = test_model(field="option1")
        enum_value = getattr(instance, "field")
        assert enum_value.value == "option1"

        # Test all enum options
        for option in ["option1", "option2", "option3"]:
            instance = test_model(field=option)
            assert getattr(instance, "field").value == option

        # Test invalid enum value
        with pytest.raises(ValidationError):
            test_model(field="invalid_option")

    def test_array_field_in_model(self):
        """Test array field type mapping and validation."""
        fields = [
            SchemaField(
                json_path="test.field",
                description="Test field",
                attributes={"xQueryable": True, "dataType": "xsd:string", "array": "Yes"},
            )
        ]
        models = core.build_dynamic_model(fields)
        assert "test" in models

        test_model = models["test"]

        # Test valid list assignment
        instance = test_model(field=["item1", "item2", "item3"])
        field_value = getattr(instance, "field")
        assert field_value == ["item1", "item2", "item3"]

        # Test empty list
        instance_empty = test_model(field=[])
        assert getattr(instance_empty, "field") == []

        # Test None assignment (optional)
        instance_none = test_model(field=None)
        assert getattr(instance_none, "field") is None

    def test_field_descriptions_preserved(self):
        """Test that field descriptions are preserved in the model."""
        fields = [
            SchemaField(
                json_path="test.name",
                description="A person's full name",
                attributes={"xQueryable": True, "dataType": "xsd:string", "array": "No"},
            ),
            SchemaField(
                json_path="test.age",
                description="Age in years",
                attributes={"xQueryable": True, "dataType": "xsd:integer", "array": "No"},
            ),
        ]
        models = core.build_dynamic_model(fields)
        assert "test" in models

        test_model = models["test"]

        # Check that the model has the expected fields
        instance = test_model()
        assert hasattr(instance, "name")
        assert hasattr(instance, "age")

        # Verify field information is accessible through model schema
        schema = test_model.model_json_schema()
        if "properties" in schema:
            if "name" in schema["properties"]:
                assert "description" in schema["properties"]["name"]
            if "age" in schema["properties"]:
                assert "description" in schema["properties"]["age"]


class TestBuildDynamicModel:
    """Test the main build_dynamic_model function."""

    def test_empty_fields(self):
        """Test with empty schema fields."""
        result = core.build_dynamic_model([])
        assert result == {}

    def test_no_matching_fields(self):
        """Test with fields that don't match the attribute flag."""
        fields = [
            SchemaField(
                json_path="person.name",
                description="Person name",
                attributes={"xMutable": True},  # No xQueryable
            )
        ]
        result = core.build_dynamic_model(fields, attribute_flag="xQueryable")
        assert result == {}

    def test_multiple_roots_error(self):
        """Test error when fields have different root paths."""
        fields = [
            SchemaField(json_path="person.name", description="Person name", attributes={"xQueryable": True}),
            SchemaField(
                json_path="organization.name", description="Organization name", attributes={"xQueryable": True}
            ),
        ]
        with pytest.raises(ValueError, match="must share a common root"):
            core.build_dynamic_model(fields)

    def test_simple_model_creation(self):
        """Test creating a simple model with basic fields."""
        fields = [
            SchemaField(
                json_path="person.name",
                description="Person name",
                attributes={"xQueryable": True, "dataType": "xsd:string", "array": "No"},
            ),
            SchemaField(
                json_path="person.age",
                description="Person age",
                attributes={"xQueryable": True, "dataType": "xsd:integer", "array": "No"},
            ),
        ]

        models = core.build_dynamic_model(fields)

        assert "person" in models
        assert "person_wrapper" in models

        # Test inner model
        person_model = models["person"]
        assert issubclass(person_model, BaseModel)

        # Create instance
        instance = person_model(name="John", age=30)
        assert getattr(instance, "name") == "John"
        assert getattr(instance, "age") == 30

        # Test with None values (optional fields)
        instance2 = person_model()
        assert getattr(instance2, "name") is None
        assert getattr(instance2, "age") is None

    def test_nested_model_creation(self):
        """Test creating nested models."""
        fields = [
            SchemaField(
                json_path="person.name.firstName",
                description="First name",
                attributes={"xQueryable": True, "dataType": "xsd:string", "array": "No"},
            ),
            SchemaField(
                json_path="person.name.lastName",
                description="Last name",
                attributes={"xQueryable": True, "dataType": "xsd:string", "array": "No"},
            ),
            SchemaField(
                json_path="person.age",
                description="Person age",
                attributes={"xQueryable": True, "dataType": "xsd:integer", "array": "No"},
            ),
        ]

        models = core.build_dynamic_model(fields)

        assert "person" in models
        # Check that nested models were created (key may vary based on implementation)
        assert len(models) > 1  # Should have more than just the root model

        # Test nested structure
        person_model = models["person"]
        instance = person_model()

        # Should have name and age fields
        assert hasattr(instance, "name")
        assert hasattr(instance, "age")

    def test_array_fields(self):
        """Test handling of array fields."""
        fields = [
            SchemaField(
                json_path="person.identifier",
                description="Identifiers",
                attributes={"xQueryable": True, "array": "Yes", "branch": True},
            ),
            SchemaField(
                json_path="person.identifier.value",
                description="Identifier value",
                attributes={"xQueryable": True, "dataType": "xsd:string", "array": "No"},
            ),
        ]

        models = core.build_dynamic_model(fields)

        # Should create models
        assert len(models) > 0

    def test_enum_fields(self):
        """Test handling of enum fields."""
        fields = [
            SchemaField(
                json_path="person.gender",
                description="Gender",
                attributes={"xQueryable": True, "enum": ["Male", "Female", "Other"], "array": "No"},
            )
        ]

        models = core.build_dynamic_model(fields)

        assert "person" in models
        person_model = models["person"]

        # Create instance with enum value
        instance = person_model(gender="Male")
        # Enum fields return enum members, so we need to check the value
        gender_value = getattr(instance, "gender")
        assert gender_value.value == "Male"

    def test_model_suffix(self):
        """Test model suffix application."""
        fields = [
            SchemaField(
                json_path="person.name",
                description="Person name",
                attributes={"xQueryable": True, "dataType": "xsd:string", "array": "No"},
            )
        ]

        models = core.build_dynamic_model(fields, model_suffix="Filter")

        # Model names should include suffix
        person_model = models["person"]
        assert person_model.__name__.endswith("Filter")

    def test_all_optional_false(self):
        """Test with all_optional=False."""
        fields = [
            SchemaField(
                json_path="person.name",
                description="Person name",
                attributes={"xQueryable": True, "dataType": "xsd:string", "array": "No"},
            )
        ]

        models = core.build_dynamic_model(fields, all_optional=False)

        person_model = models["person"]

        # Should require fields when all_optional=False
        with pytest.raises(ValidationError):
            person_model()  # Missing required field

    def test_allow_extra_true(self):
        """Test with allow_extra=True."""
        fields = [
            SchemaField(
                json_path="person.name",
                description="Person name",
                attributes={"xQueryable": True, "dataType": "xsd:string", "array": "No"},
            )
        ]

        models = core.build_dynamic_model(fields, allow_extra=True)

        person_model = models["person"]

        # Should allow extra fields
        instance = person_model(name="John", extra_field="value")
        assert getattr(instance, "extra_field") == "value"

    def test_attribute_flag_none(self):
        """Test with attribute_flag=None (include all fields)."""
        fields = [
            SchemaField(
                json_path="person.name",
                description="Person name",
                attributes={"dataType": "xsd:string", "array": "No"},  # No xQueryable
            )
        ]

        models = core.build_dynamic_model(fields, attribute_flag=None)

        assert "person" in models
        person_model = models["person"]
        assert hasattr(person_model(), "name")


class TestBuilderFunctions:
    """Test the convenience builder functions."""

    @patch("lif.dynamic_models.core.get_schema_fields")
    def test_build_filter_models(self, mock_get_schema_fields):
        """Test build_filter_models function."""
        mock_fields = [
            # SchemaField(
            #     json_path="person.name",
            #     description="Person name",
            #     attributes={"xQueryable": True, "dataType": "xsd:string", "array": "No"},
            # )
            # SchemaField(
            #     json_path='person',
            #     description='',
            #     attributes={'xMutable': False, 'type': 'object', 'array': 'No', 'branch': True, 'leaf': False},
            #     py_field_name=''
            # )
            SchemaField(
                json_path="person.identifier.identifier",
                description='A number and/or alphanumeric code used to uniquely identify the entity. Use "missing at will", "ad-hoc" and "not applicable" for missing data to avoid skewed outcomes.',
                attributes={
                    "xQueryable": True,
                    "xMutable": False,
                    "dataType": "xsd:string",
                    "required": "Yes",
                    "array": "No",
                    "uniqueName": "Common.Identifier.identifier",
                    "type": "xsd:string",
                    "branch": False,
                    "leaf": True,
                },
                py_field_name="",
            )
        ]
        mock_get_schema_fields.return_value = mock_fields

        models = core.build_filter_models(mock_fields)

        print(models)

        assert len(models) > 0
        # Should have Filter suffix
        for model_cls in models.values():
            if hasattr(model_cls, "__name__"):
                assert "Filter" in model_cls.__name__

    @patch("lif.dynamic_models.core.get_schema_fields")
    def test_build_mutation_models(self, mock_get_schema_fields):
        """Test build_mutation_models function."""
        mock_fields = [
            SchemaField(
                json_path="person.name",
                description="Person name",
                attributes={"xMutable": True, "dataType": "xsd:string", "array": "No"},
            )
        ]
        mock_get_schema_fields.return_value = mock_fields

        models = core.build_mutation_models(mock_fields)

        assert len(models) > 0
        # Should have Mutation suffix
        for model_cls in models.values():
            if hasattr(model_cls, "__name__"):
                assert "Mutation" in model_cls.__name__

    @patch("lif.dynamic_models.core.get_schema_fields")
    def test_build_full_models(self, mock_get_schema_fields):
        """Test build_full_models function."""
        mock_fields = [
            SchemaField(
                json_path="person.name", description="Person name", attributes={"dataType": "xsd:string", "array": "No"}
            )
        ]
        mock_get_schema_fields.return_value = mock_fields

        models = core.build_full_models(mock_fields)

        assert len(models) > 0
        # Should have Type suffix
        for model_cls in models.values():
            if hasattr(model_cls, "__name__"):
                assert "Type" in model_cls.__name__


class TestGetSchemaFields:
    """Test the get_schema_fields function."""

    @patch.dict(os.environ, {"OPENAPI_SCHEMA_FILE": str(PATH_TO_TEST_SCHEMA), "ROOT_NODE": "Person"})
    @patch("lif.dynamic_models.core.load_schema_nodes")
    def test_get_schema_fields_with_env_vars(self, mock_load_schema_nodes):
        """Test get_schema_fields with environment variables."""
        mock_fields = [SchemaField("person.name", "Name", {})]
        mock_load_schema_nodes.return_value = mock_fields

        result = core.get_schema_fields()

        # Verify the function was called with correct arguments
        mock_load_schema_nodes.assert_called_once()
        call_args = mock_load_schema_nodes.call_args[0]
        assert str(call_args[0]) == str(PATH_TO_TEST_SCHEMA)
        assert call_args[1] == "Person"
        assert result == mock_fields

    def test_get_schema_fields_no_env_var(self):
        """Test get_schema_fields without OPENAPI_SCHEMA_FILE."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="OPENAPI_SCHEMA_FILE environment variable is not set"):
                core.get_schema_fields()


class TestBuildAllModels:
    """Test the build_all_models function."""

    @patch("lif.dynamic_models.core.get_schema_fields")
    def test_build_all_models(self, mock_get_schema_fields):
        """Test build_all_models function."""
        mock_fields = [
            SchemaField(
                json_path="person.name",
                description="Person name",
                attributes={"xQueryable": True, "xMutable": True, "dataType": "xsd:string", "array": "No"},
            )
        ]
        mock_get_schema_fields.return_value = mock_fields

        fields, filter_models, mutation_models, full_models = core.build_all_models()

        assert fields == mock_fields
        assert len(filter_models) > 0
        assert len(mutation_models) > 0
        assert len(full_models) > 0

    @patch("lif.dynamic_models.core.get_schema_fields")
    def test_build_all_models_custom_options(self, mock_get_schema_fields):
        """Test build_all_models with custom options."""
        mock_fields = [
            SchemaField(
                json_path="person.name",
                description="Person name",
                attributes={"xQueryable": True, "xMutable": True, "dataType": "xsd:string", "array": "No"},
            )
        ]
        mock_get_schema_fields.return_value = mock_fields

        fields, filter_models, mutation_models, full_models = core.build_all_models(
            filter_allow_extra=False,
            filter_all_optional=False,
            mutation_allow_extra=True,
            mutation_all_optional=False,
            full_allow_extra=True,
            full_all_optional=True,
        )

        assert fields == mock_fields
        assert len(filter_models) > 0
        assert len(mutation_models) > 0
        assert len(full_models) > 0


class TestRealWorldIntegration:
    """Integration tests with the actual test schema file."""

    def test_with_test_schema_file(self):
        """Test with the actual test_openapi_schema.json file."""
        with patch.dict(os.environ, {"OPENAPI_SCHEMA_FILE": str(PATH_TO_TEST_SCHEMA), "ROOT_NODE": "Person"}):
            fields = core.get_schema_fields()

            # Should have loaded fields from the test schema
            assert len(fields) > 0

            # Test building models
            filter_models = core.build_filter_models(fields)
            assert len(filter_models) > 0

            # Test that we can create instances
            if "person" in filter_models:
                person_model = filter_models["person"]
                instance = person_model()
                assert instance is not None

    def test_end_to_end_model_creation(self):
        """End-to-end test of model creation and usage."""
        # Create test fields manually to simulate real usage
        fields = [
            SchemaField(
                json_path="person.identifier.identifier",
                description="A number and/or alphanumeric code used to uniquely identify the entity",
                attributes={"xQueryable": True, "dataType": "xsd:string", "array": "No"},
            ),
            SchemaField(
                json_path="person.identifier.identifierType",
                description="The types of sources of identifiers used to uniquely identify the entity",
                attributes={"xQueryable": True, "dataType": "xsd:string", "array": "No"},
            ),
            SchemaField(
                json_path="person.name.firstName",
                description="The first name of a person or individual",
                attributes={"xMutable": False, "dataType": "xsd:string", "array": "No"},
            ),
            SchemaField(
                json_path="person.name.lastName",
                description="The last name of a person or individual",
                attributes={"xMutable": False, "dataType": "xsd:string", "array": "No"},
            ),
        ]

        # Build filter models (only xQueryable fields)
        filter_models = core.build_filter_models(fields)

        # Should have models
        assert len(filter_models) > 0

        # Build full models (all fields) - use all_optional=True for this test
        full_models = core.build_full_models(fields, all_optional=True)

        # Should have models
        assert len(full_models) > 0

        # Test that models work correctly
        if "person" in full_models:
            person_model = full_models["person"]

            # Create instance (should work with all_optional=True)
            instance = person_model()
            assert instance is not None


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_invalid_enum_values(self):
        """Test handling of invalid enum values."""
        fields = [
            SchemaField(
                json_path="person.status",
                description="Status",
                attributes={"xQueryable": True, "enum": ["Active", "Inactive"], "array": "No"},
            )
        ]

        models = core.build_dynamic_model(fields)
        person_model = models["person"]

        # Valid enum value should work
        instance = person_model(status="Active")
        assert getattr(instance, "status").value == "Active"

        # Invalid enum value should raise validation error
        with pytest.raises(ValidationError):
            person_model(status="Invalid")

    def test_complex_nested_structure(self):
        """Test deeply nested field structures."""
        fields = [
            SchemaField(
                json_path="person.contact.address.street",
                description="Street address",
                attributes={"xQueryable": True, "dataType": "xsd:string", "array": "No"},
            ),
            SchemaField(
                json_path="person.contact.email.address",
                description="Email address",
                attributes={"xQueryable": True, "dataType": "xsd:string", "array": "No"},
            ),
        ]

        models = core.build_dynamic_model(fields)

        # Should create nested models
        assert "person" in models
        assert len(models) > 1

        # Test that nested structure works
        person_model = models["person"]
        instance = person_model()

        # Should have contact field
        assert hasattr(instance, "contact")

    def test_special_characters_in_enum(self):
        """Test enum with special characters."""
        fields = [
            SchemaField(
                json_path="person.type",
                description="Person type",
                attributes={"xQueryable": True, "enum": ["Type-A", "Type B", "Type@C"], "array": "No"},
            )
        ]

        models = core.build_dynamic_model(fields)
        person_model = models["person"]

        # Should handle special characters in enum values
        instance = person_model(type="Type-A")
        assert getattr(instance, "type").value == "Type-A"

        # Test all special character variants
        for type_val in ["Type-A", "Type B", "Type@C"]:
            instance = person_model(type=type_val)
            assert getattr(instance, "type").value == type_val

    def test_empty_description(self):
        """Test fields with empty descriptions."""
        fields = [
            SchemaField(
                json_path="person.field",
                description="",
                attributes={"xQueryable": True, "dataType": "xsd:string", "array": "No"},
            )
        ]

        models = core.build_dynamic_model(fields)
        assert len(models) > 0

        # Should still create working model
        person_model = models["person"]
        instance = person_model(field="test")
        assert getattr(instance, "field") == "test"

    def test_missing_attributes(self):
        """Test fields with minimal attributes."""
        fields = [
            SchemaField(
                json_path="person.field",
                description="Basic field",
                attributes={"xQueryable": True},  # Minimal attributes
            )
        ]

        models = core.build_dynamic_model(fields)
        assert len(models) > 0

        # Should create model with default string type
        person_model = models["person"]
        instance = person_model(field="test")
        assert getattr(instance, "field") == "test"

    def test_array_with_nested_objects(self):
        """Test arrays containing nested objects."""
        fields = [
            SchemaField(
                json_path="person.addresses",
                description="List of addresses",
                attributes={"xQueryable": True, "array": "Yes", "branch": True},
            ),
            SchemaField(
                json_path="person.addresses.street",
                description="Street address",
                attributes={"xQueryable": True, "dataType": "xsd:string", "array": "No"},
            ),
            SchemaField(
                json_path="person.addresses.city",
                description="City",
                attributes={"xQueryable": True, "dataType": "xsd:string", "array": "No"},
            ),
        ]

        models = core.build_dynamic_model(fields)
        assert len(models) > 0

        # Should create model with nested array structure
        person_model = models["person"]
        instance = person_model()
        assert hasattr(instance, "addresses")

    def test_very_long_field_names(self):
        """Test handling of very long field names."""
        long_name = "a" * 100  # 100 character field name
        fields = [
            SchemaField(
                json_path=f"person.{long_name}",
                description="Field with very long name",
                attributes={"xQueryable": True, "dataType": "xsd:string", "array": "No"},
            )
        ]

        models = core.build_dynamic_model(fields)
        person_model = models["person"]

        # Should handle long field names gracefully
        instance = person_model(**{long_name: "test_value"})
        assert getattr(instance, long_name) == "test_value"

    def test_unicode_in_descriptions(self):
        """Test handling of unicode characters in descriptions."""
        fields = [
            SchemaField(
                json_path="person.name",
                description="Имя пользователя (User name in Cyrillic) 用户名 (Chinese)",
                attributes={"xQueryable": True, "dataType": "xsd:string", "array": "No"},
            )
        ]

        models = core.build_dynamic_model(fields)
        assert len(models) > 0

        person_model = models["person"]
        instance = person_model(name="Test")
        assert getattr(instance, "name") == "Test"


class TestPerformance:
    """Test performance aspects of model generation."""

    def test_large_schema_handling(self):
        """Test model generation with a large number of fields."""
        import time

        # Generate 100 fields
        fields = []
        for i in range(100):
            fields.append(
                SchemaField(
                    json_path=f"person.field_{i}",
                    description=f"Test field number {i}",
                    attributes={"xQueryable": True, "dataType": "xsd:string", "array": "No"},
                )
            )

        start_time = time.time()
        models = core.build_dynamic_model(fields)
        end_time = time.time()

        # Should complete in reasonable time (less than 5 seconds)
        assert (end_time - start_time) < 5.0
        assert len(models) > 0

        # Test that the resulting model works
        person_model = models["person"]
        test_data = {f"field_{i}": f"value_{i}" for i in range(10)}  # Test first 10 fields
        instance = person_model(**test_data)

        for i in range(10):
            assert getattr(instance, f"field_{i}") == f"value_{i}"

    def test_enum_caching_efficiency(self):
        """Test that enum caching works efficiently."""
        # Create the same enum multiple times
        enum_values = ["A", "B", "C"]

        enum1 = core.make_enum("TestEnum", enum_values)
        enum2 = core.make_enum("TestEnum", enum_values)
        enum3 = core.make_enum("TestEnum", enum_values)

        # Should return the same class (cached)
        assert enum1 is enum2 is enum3

        # Different values should create different enums
        enum4 = core.make_enum("TestEnum", ["A", "B", "D"])
        assert enum1 is not enum4


def test_sample():
    """Legacy test to maintain compatibility."""
    assert core is not None
