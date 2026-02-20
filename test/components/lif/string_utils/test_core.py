from datetime import date, datetime

from lif.string_utils import (
    safe_identifier,
    to_pascal_case,
    to_snake_case,
    to_camel_case,
    dict_keys_to_snake,
    dict_keys_to_camel,
    convert_dates_to_strings,
    to_value_enum_name,
)


class TestSafeIdentifier:
    def test_special_chars_replaced(self):
        assert safe_identifier("First Name") == "first_name"
        assert safe_identifier("first-name") == "first_name"
        assert safe_identifier("first$name") == "first_name"

    def test_leading_digit_prefixed(self):
        assert safe_identifier("123abc") == "_123abc"

    def test_camel_case_boundaries(self):
        assert safe_identifier("CamelCase") == "camel_case"
        assert safe_identifier("camelCaseABC") == "camel_case_abc"

    def test_consecutive_underscores_collapsed(self):
        """Regression: CamelCase splitting + special chars should not produce double underscores."""
        assert safe_identifier("some--thing") == "some_thing"
        assert safe_identifier("A__B") == "a_b"


class TestToPascalCase:
    def test_from_snake_case(self):
        assert to_pascal_case("hello_world") == "HelloWorld"

    def test_multiple_parts(self):
        assert to_pascal_case("hello", "world") == "HelloWorld"


class TestToSnakeCase:
    def test_from_camel_and_pascal(self):
        assert to_snake_case("CamelCase") == "camel_case"
        assert to_snake_case("camelCase") == "camel_case"

    def test_acronym_boundaries(self):
        """Acronyms like HTTP and ID should split correctly at boundaries."""
        assert to_snake_case("HTTPServerID") == "http_server_id"


class TestToCamelCase:
    def test_from_snake_case(self):
        assert to_camel_case("hello_world") == "helloWorld"

    def test_lowercases_first_letter(self):
        assert to_camel_case("HelloWorld") == "helloWorld"


class TestDictKeyTransforms:
    def test_nested_keys_to_snake(self):
        """Recursion through nested dicts and lists."""
        data = {"FirstName": "Alice", "Address": {"zipCode": 12345}, "items": [{"itemID": 1}]}
        out = dict_keys_to_snake(data)
        assert out == {"first_name": "Alice", "address": {"zip_code": 12345}, "items": [{"item_id": 1}]}

    def test_nested_keys_to_camel(self):
        """Recursion through nested dicts and lists."""
        data = {"first_name": "Bob", "address": {"zip_code": 12345}, "items": [{"item_id": 1}]}
        out = dict_keys_to_camel(data)
        assert out == {"firstName": "Bob", "address": {"zipCode": 12345}, "items": [{"itemId": 1}]}


class TestConvertDatesToStrings:
    def test_nested_dates_and_datetimes(self):
        """Type dispatch: date and datetime converted, other types preserved."""
        d = date(2020, 1, 2)
        dt = datetime(2020, 1, 2, 3, 4, 5)
        obj = {"when": d, "arr": [dt, {"n": 1}]}
        out = convert_dates_to_strings(obj)
        assert out == {"when": d.isoformat(), "arr": [dt.isoformat(), {"n": 1}]}


class TestToValueEnumName:
    def test_special_chars_and_leading_digits(self):
        assert to_value_enum_name("in progress") == "IN_PROGRESS"
        assert to_value_enum_name("done!") == "DONE_"
        assert to_value_enum_name("123start") == "_123START"
