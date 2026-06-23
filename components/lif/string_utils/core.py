import re
from typing import Any
from datetime import date, datetime

from lif.logging import get_logger

logger = get_logger(__name__)


def safe_identifier(name: str) -> str:
    """Convert any string to a safe Python identifier (snake_case, no special chars).

    Args:
        name (str): The input name string.

    Returns:
        str: A valid Python identifier.
    """
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    s2 = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1)
    safe = re.sub(r"\W|^(?=\d)", "_", s2)
    safe = re.sub(r"_+", "_", safe)  # Collapse consecutive underscores
    return safe.lower()


def safe_graphql_name(name: str) -> str:
    """Sanitize a string into a valid GraphQL name, preserving its original casing.

    GraphQL names must match /[_A-Za-z][_0-9A-Za-z]*/ — only ``[_0-9A-Za-z]`` and not
    leading with a digit. Unlike :func:`safe_identifier` (which snake_cases for Python
    attributes), this keeps the original casing so the exposed GraphQL field/type name stays
    as close to the source schema as possible; it only replaces invalid characters with ``_``
    and prefixes ``_`` when the name would start with a digit.

    Without this, a single source-schema name containing an illegal character (e.g. a hyphen,
    ``iSO639-2LangCode``) makes the entire GraphQL schema build raise ``GraphQLError`` and
    crashes the service (see issue #1011).
    """
    if not name:
        return name
    safe = re.sub(r"[^_0-9A-Za-z]", "_", name)
    if safe[0].isdigit():
        safe = f"_{safe}"
    return safe


def to_pascal_case(*parts: str) -> str:
    """Convert strings or parts to PascalCase.

    Args:
        *parts (str): Parts to be converted.

    Returns:
        str: PascalCase string.
    """
    return "".join("".join(word.capitalize() for word in part.split("_")) for part in parts if part)


def to_snake_case(name: str) -> str:
    """Converts CamelCase or PascalCase to snake_case."""
    s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def to_camel_case(s: str) -> str:
    """Converts snake_case to lowerCamelCase."""
    if not s:
        return s
    if "_" in s:
        parts = s.lower().split("_")
        return parts[0] + "".join(word.capitalize() for word in parts[1:])
    return s[0].lower() + s[1:]


def camelcase_path(path: str) -> str:
    """Convert a dotted path string to camelCase segments.

    Args:
        path: The dot-separated path.

    Returns:
        The camelCase path.
    """
    return ".".join([to_camel_case(p) for p in path.split(".")])


def dict_keys_to_snake(obj: Any) -> Any:
    """Recursively converts dict keys to snake_case."""
    if isinstance(obj, list):
        return [dict_keys_to_snake(item) for item in obj]
    if isinstance(obj, dict):
        return {to_snake_case(k): dict_keys_to_snake(v) for k, v in obj.items()}
    return obj


def dict_keys_to_camel(obj: Any) -> Any:
    """Recursively converts dict keys to camelCase."""
    if isinstance(obj, list):
        return [dict_keys_to_camel(item) for item in obj]
    if isinstance(obj, dict):
        return {to_camel_case(k): dict_keys_to_camel(v) for k, v in obj.items()}
    return obj


def convert_dates_to_strings(obj: Any) -> Any:
    """Recursively converts dict date and datetime to strings."""
    if isinstance(obj, dict):
        return {k: convert_dates_to_strings(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_dates_to_strings(item) for item in obj]
    elif isinstance(obj, (date, datetime)):
        return obj.isoformat()
    else:
        return obj


def to_value_enum_name(label: str) -> str:
    """Convert a string label to a valid Python Enum name."""
    key = str(label).upper()
    key = re.sub(r"\W|^(?=\d)", "_", key)
    return key
