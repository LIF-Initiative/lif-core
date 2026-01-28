"""Data validation utilities for the LIF system."""

from typing import Any, Set

# Truthy value constants
TRUTHY_VALUES: Set[str] = {"1", "true", "yes", "on", "y"}
FALSY_VALUES: Set[str] = {"0", "false", "no", "off", "n"}


def is_truthy(value: Any) -> bool:
    """Check if a value represents a truthy state.

    Args:
        value: The value to evaluate (string, bool, int, etc.)

    Returns:
        bool: True if the value is considered truthy

    Examples:
        >>> is_truthy("yes")
        True
        >>> is_truthy("1")
        True
        >>> is_truthy("false")
        False
        >>> is_truthy(None)
        False
    """
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in TRUTHY_VALUES


def is_falsy(value: Any) -> bool:
    """Check if a value represents a falsy state.

    Args:
        value: The value to evaluate

    Returns:
        bool: True if the value is considered falsy
    """
    if value is None:
        return True
    if isinstance(value, bool):
        return not value
    return str(value).strip().lower() in FALSY_VALUES


def to_bool(value: Any, default: bool = False) -> bool:
    """Convert a value to boolean with explicit truthy/falsy evaluation.

    Args:
        value: The value to convert
        default: Default value if the input is ambiguous

    Returns:
        bool: The boolean representation
    """
    if is_truthy(value):
        return True
    if is_falsy(value):
        return False
    return default
