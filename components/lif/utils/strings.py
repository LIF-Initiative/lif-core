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
    # Replace any non-word characters with spaces to isolate tokens
    cleaned = re.sub(r"[^0-9A-Za-z]+", " ", name).strip()

    tokens: list[str] = []
    for chunk in cleaned.split():
        # If the chunk contains camel-case boundaries or acronym patterns, split accordingly
        if re.search(r"[a-z][A-Z]", chunk) or re.search(r"[A-Z]{2,}[a-z]", chunk):
            # Use standard camelCase -> snake_case splitting for such chunks
            s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", chunk)
            s2 = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1)
            tokens.append(s2.lower())
        else:
            tokens.append(chunk.lower())

    # Join with single underscores
    result = "_".join(t for t in tokens if t)
    # If result starts with a digit, prefix underscore
    if result and result[0].isdigit():
        result = f"_{result}"
    return result


def to_pascal_case(*parts: str) -> str:
    """Convert strings or parts to PascalCase.

    Accepts any number of string parts. Each part can contain spaces, dashes,
    underscores, or mixed case; all will be tokenized and joined as PascalCase.

    Args:
        *parts (str): Parts to be converted.

    Returns:
        str: PascalCase string.
    """
    tokens: list[str] = []
    for p in parts:
        if not p:
            continue
        s = p.replace("-", " ").replace("_", " ")
        # Capture standard words, all-caps acronyms, and numbers
        tokens += re.findall(r"[A-Za-z][a-z]*|[A-Z]+(?![a-z])|\d+", s)
    return "".join(t[:1].upper() + t[1:] for t in tokens)


def to_snake_case(name: str) -> str:
    """Converts CamelCase or PascalCase to snake_case."""
    s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def to_camel_case(s: str) -> str:
    """Convert string to lower camelCase."""
    s = re.sub(r"([_\-\s]+)([a-zA-Z])", lambda m: m.group(2).upper(), s)
    if not s:
        return s
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
