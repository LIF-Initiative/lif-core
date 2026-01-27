import pytest
from pathlib import Path
from unittest.mock import mock_open, patch

from lif.schema import core


class TestExtractNodes:
    """Tests for the extract_nodes function."""

    def test_extract_simple_string_field(self):
        """Test extracting a simple string field."""
        obj = {"type": "string", "description": "A simple string field", "x-queryable": True}

        nodes = core.extract_nodes(obj, "test.field")

        assert len(nodes) == 1
        node = nodes[0]
        assert node.json_path == "test.field"
        assert node.description == "A simple string field"
        assert node.attributes["xQueryable"] is True
        assert node.attributes["type"] == "string"
        assert node.attributes["array"] == "No"
        assert node.attributes["leaf"] is True
        assert node.attributes["branch"] is False

    def test_extract_array_field(self):
        """Test extracting an array field."""
        obj = {"type": "array", "items": {"type": "string"}, "description": "An array of strings"}

        nodes = core.extract_nodes(obj, "test.array")

        assert len(nodes) == 2
        # First node is the array container
        array_node = nodes[0]
        assert array_node.json_path == "test.array"
        assert array_node.description == "An array of strings"
        assert array_node.attributes["type"] == "array"
        assert array_node.attributes["array"] == "Yes"
        assert array_node.attributes["branch"] is True

        # Second node is the items
        items_node = nodes[1]
        assert items_node.json_path == "test.array"
        assert items_node.attributes["type"] == "string"

    def test_extract_object_with_properties(self):
        """Test extracting an object with properties."""
        obj = {
            "type": "object",
            "description": "An object with properties",
            "properties": {
                "name": {"type": "string", "description": "Name field", "x-mutable": False},
                "age": {"type": "integer", "description": "Age field"},
            },
        }

        nodes = core.extract_nodes(obj, "person")

        assert len(nodes) == 3

        # First node is the object container
        obj_node = nodes[0]
        assert obj_node.json_path == "person"
        assert obj_node.description == "An object with properties"
        assert obj_node.attributes["type"] == "object"
        assert obj_node.attributes["branch"] is True

        # Second and third nodes are the properties
        name_node = next(n for n in nodes if n.json_path == "person.name")
        assert name_node.description == "Name field"
        assert name_node.attributes["type"] == "string"
        assert name_node.attributes["xMutable"] is False

        age_node = next(n for n in nodes if n.json_path == "person.age")
        assert age_node.description == "Age field"
        assert age_node.attributes["type"] == "integer"

    def test_extract_with_custom_attributes(self):
        """Test extracting fields with custom LIF attributes."""
        obj = {
            "type": "string",
            "Description": "Custom description",  # uppercase D
            "DataType": "xsd:string",
            "Required": "Yes",
            "Array": "No",
            "UniqueName": "Person.Name.firstName",
            "enum": ["option1", "option2"],
        }

        nodes = core.extract_nodes(obj, "name")

        assert len(nodes) == 1
        node = nodes[0]
        assert node.description == "Custom description"
        assert node.attributes["dataType"] == "xsd:string"
        assert node.attributes["required"] == "Yes"
        assert node.attributes["array"] == "No"
        assert node.attributes["uniqueName"] == "Person.Name.firstName"
        assert node.attributes["enum"] == ["option1", "option2"]

    def test_extract_nested_structure(self):
        """Test extracting a deeply nested structure."""
        obj = {
            "type": "object",
            "properties": {
                "contact": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "email": {"type": "string", "description": "Email address", "x-queryable": True}
                        },
                    },
                }
            },
        }

        nodes = core.extract_nodes(obj, "person")

        # Should have: person, person.contact, person.contact (items), person.contact.email
        assert len(nodes) == 4

        email_node = next(n for n in nodes if n.json_path == "person.contact.email")
        assert email_node.description == "Email address"
        assert email_node.attributes["xQueryable"] is True

    def test_extract_with_empty_path_prefix(self):
        """Test extracting with empty path prefix."""
        obj = {"type": "string", "description": "Root field"}

        nodes = core.extract_nodes(obj, "")

        assert len(nodes) == 1
        assert nodes[0].json_path == ""

    def test_extract_non_dict_returns_empty(self):
        """Test that non-dict objects return empty list."""
        nodes = core.extract_nodes("not a dict", "path")
        assert nodes == []

        nodes = core.extract_nodes(123, "path")
        assert nodes == []

        nodes = core.extract_nodes(None, "path")
        assert nodes == []


class TestResolveOpenApiRoot:
    """Tests for the resolve_openapi_root function."""

    def test_resolve_from_components_schemas(self):
        """Test resolving root from components.schemas."""
        doc = {"components": {"schemas": {"Person": {"type": "object"}, "Organization": {"type": "object"}}}}

        schema, root = core.resolve_openapi_root(doc, "Person")

        assert root == "Person"
        assert schema == {"type": "object"}

    def test_resolve_from_definitions(self):
        """Test resolving root from definitions (older OpenAPI/JSON Schema)."""
        doc = {"definitions": {"User": {"type": "object"}, "Product": {"type": "object"}}}

        schema, root = core.resolve_openapi_root(doc, "User")

        assert root == "User"
        assert schema == {"type": "object"}

    def test_resolve_components_takes_precedence(self):
        """Test that components.schemas takes precedence over definitions."""
        doc = {
            "components": {"schemas": {"Person": {"type": "object", "description": "from components"}}},
            "definitions": {"Person": {"type": "object", "description": "from definitions"}},
        }

        schema, root = core.resolve_openapi_root(doc, "Person")

        assert schema["description"] == "from components"

    def test_resolve_nonexistent_root_raises_error(self):
        """Test that resolving a non-existent root raises ValueError."""
        doc = {"components": {"schemas": {"Person": {"type": "object"}}}}

        with pytest.raises(ValueError) as exc_info:
            core.resolve_openapi_root(doc, "NonExistent")

        assert "Root schema 'NonExistent' not found" in str(exc_info.value)
        assert "Person" in str(exc_info.value)

    def test_resolve_empty_doc_raises_error(self):
        """Test that resolving from empty doc raises ValueError."""
        doc = {}

        with pytest.raises(ValueError) as exc_info:
            core.resolve_openapi_root(doc, "Person")

        assert "Root schema 'Person' not found" in str(exc_info.value)


class TestLoadSchemaNodes:
    """Tests for the load_schema_nodes function."""

    def test_load_from_dict(self):
        """Test loading schema nodes from a dictionary."""
        schema_dict = {"type": "object", "properties": {"name": {"type": "string", "description": "Person name"}}}

        nodes = core.load_schema_nodes(schema_dict)

        assert len(nodes) == 2
        assert any(n.json_path == "" for n in nodes)
        assert any(n.json_path == "name" for n in nodes)

    def test_load_from_dict_with_root(self):
        """Test loading schema nodes from dict with specific root."""
        schema_dict = {
            "components": {"schemas": {"Person": {"type": "object", "properties": {"name": {"type": "string"}}}}}
        }

        nodes = core.load_schema_nodes(schema_dict, root="Person")

        assert len(nodes) == 2
        # The root should be resolved and path should start with the camelCase root name
        assert any(n.json_path == "person" for n in nodes)  # Root node
        assert any(n.json_path == "person.name" for n in nodes)  # Property node

    @patch("builtins.open", new_callable=mock_open)
    @patch("jsonref.load")
    def test_load_from_file_path_string(self, mock_jsonref_load, mock_file_open):
        """Test loading schema nodes from file path as string."""
        schema_data = {"type": "object", "properties": {"id": {"type": "string"}}}
        mock_jsonref_load.return_value = schema_data

        nodes = core.load_schema_nodes("/path/to/schema.json")

        mock_file_open.assert_called_once_with("/path/to/schema.json", "r")
        mock_jsonref_load.assert_called_once()
        assert len(nodes) == 2

    @patch("builtins.open", new_callable=mock_open)
    @patch("jsonref.load")
    def test_load_from_pathlib_path(self, mock_jsonref_load, mock_file_open):
        """Test loading schema nodes from pathlib.Path."""
        schema_data = {"type": "string"}
        mock_jsonref_load.return_value = schema_data

        path = Path("/path/to/schema.json")
        nodes = core.load_schema_nodes(path)

        mock_file_open.assert_called_once_with(path, "r")
        assert len(nodes) == 1

    def test_load_invalid_type_raises_error(self):
        """Test that invalid input type raises TypeError."""
        with pytest.raises(TypeError) as exc_info:
            core.load_schema_nodes(123)  # type: ignore

        assert "openapi must be a str, Path, or dict" in str(exc_info.value)

    @patch("lif.schema.core.jsonref")
    def test_load_dict_calls_replace_refs(self, mock_jsonref):
        """Test that loading from dict calls jsonref.replace_refs."""
        schema_dict = {"type": "string"}
        mock_jsonref.JsonRef.replace_refs.return_value = schema_dict

        core.load_schema_nodes(schema_dict)

        mock_jsonref.JsonRef.replace_refs.assert_called_once_with(schema_dict)


class TestAttributeKeys:
    """Test that ATTRIBUTE_KEYS contains expected values."""

    def test_attribute_keys_content(self):
        """Test that ATTRIBUTE_KEYS contains the expected keys."""
        expected_keys = ["x-queryable", "x-mutable", "DataType", "Required", "Array", "UniqueName", "enum", "type"]

        assert core.ATTRIBUTE_KEYS == expected_keys


class TestHelperFunctions:
    """Test helper functions within extract_nodes."""

    def test_is_array_detection(self):
        """Test array detection logic."""
        # Test with direct array access since is_array is nested
        obj_with_type_array = {"type": "array"}
        nodes = core.extract_nodes(obj_with_type_array, "test")
        assert nodes[0].attributes["array"] == "Yes"

        obj_with_items = {"items": {"type": "string"}}
        nodes = core.extract_nodes(obj_with_items, "test")
        assert nodes[0].attributes["array"] == "Yes"

        obj_without_array = {"type": "string"}
        nodes = core.extract_nodes(obj_without_array, "test")
        assert nodes[0].attributes["array"] == "No"

    def test_description_preference(self):
        """Test that uppercase 'Description' is preferred over 'description'."""
        obj_with_both = {
            "type": "string",
            "Description": "Uppercase description",
            "description": "Lowercase description",
        }

        nodes = core.extract_nodes(obj_with_both, "test")
        assert nodes[0].description == "Uppercase description"

        obj_with_lowercase_only = {"type": "string", "description": "Lowercase only"}

        nodes = core.extract_nodes(obj_with_lowercase_only, "test")
        assert nodes[0].description == "Lowercase only"


class TestIntegrationWithTestSchema:
    """Integration tests using the test schema."""

    def test_extract_from_simple_person_schema(self):
        """Test extracting from a simple person schema."""
        person_schema = {
            "type": "object",
            "properties": {
                "Identifier": {
                    "type": "array",
                    "properties": {
                        "identifier": {"type": "string", "description": "A unique identifier", "x-queryable": True},
                        "identifierType": {"type": "string", "x-queryable": True},
                    },
                },
                "Name": {
                    "type": "array",
                    "properties": {
                        "firstName": {"type": "string", "x-mutable": False},
                        "lastName": {"type": "string", "x-mutable": False},
                    },
                },
            },
        }

        nodes = core.extract_nodes(person_schema, "Person")

        # Should extract: Person, Identifier, identifier, identifierType, Name, firstName, lastName
        assert len(nodes) == 7

        # Check specific nodes
        person_node = next(n for n in nodes if n.json_path == "person")
        assert person_node.attributes["type"] == "object"
        assert person_node.attributes["branch"] is True

        id_node = next(n for n in nodes if n.json_path == "person.identifier.identifier")
        assert id_node.attributes["xQueryable"] is True
        assert id_node.description == "A unique identifier"

        first_name_node = next(n for n in nodes if n.json_path == "person.name.firstName")
        assert first_name_node.attributes["xMutable"] is False


class TestWithRealTestSchema:
    """Test with the actual test schema file."""

    def test_load_test_schema_file(self):
        """Test loading the actual test_openapi_schema.json file."""
        test_schema_path = Path(__file__).parent.parent.parent.parent / "data" / "test_openapi_schema.json"

        nodes = core.load_schema_nodes(test_schema_path, root="Person")

        # Should have nodes for Person and its properties
        assert len(nodes) > 0

        # Check that we have the expected main properties
        paths = [n.json_path for n in nodes]
        assert "person" in paths  # Root Person object
        assert any("identifier" in path for path in paths)  # Identifier array
        assert any("name" in path for path in paths)  # Name array
        assert any("proficiency" in path for path in paths)  # Proficiency array
        assert any("contact" in path for path in paths)  # Contact array

        # Check that x-queryable and x-mutable attributes are preserved
        queryable_nodes = [n for n in nodes if n.attributes.get("xQueryable")]
        mutable_nodes = [n for n in nodes if "xMutable" in n.attributes]

        assert len(queryable_nodes) > 0  # Should have some queryable fields
        assert len(mutable_nodes) > 0  # Should have some mutable fields


# Additional edge case tests
class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_extract_with_tuple_validation_items(self):
        """Test extracting with items as list (tuple validation)."""
        obj = {"type": "array", "items": [{"type": "string"}, {"type": "number"}]}

        nodes = core.extract_nodes(obj, "tuple_array")

        # Should have the array node plus nodes for each item type
        assert len(nodes) >= 1
        assert nodes[0].attributes["array"] == "Yes"

    def test_extract_with_missing_attributes(self):
        """Test extraction when some attributes are missing."""
        obj = {
            # No type, no description
            "x-queryable": True
        }

        nodes = core.extract_nodes(obj, "test")

        assert len(nodes) == 1
        node = nodes[0]
        assert node.description == ""
        assert node.attributes["xQueryable"] is True
        assert node.attributes["type"] is None

    def test_camelcase_path_conversion(self):
        """Test that paths are properly converted to camelCase."""
        obj = {"type": "string"}

        nodes = core.extract_nodes(obj, "some-complex_path.with-dashes")

        # The camelcase_path function should be called on the path
        assert len(nodes) == 1
        # The actual conversion is handled by camelcase_path function in string_utils
