"""
XSD to Python type mappings for LIF schema processing.

This centralizes type mappings used across:
- openapi_to_graphql/type_factory.py
- semantic_search_service/core.py
- Any future schema processing components
"""

from datetime import date, datetime
from typing import Any, Dict, Type


# Canonical XSD to Python type mapping
# Used by GraphQL type generation, semantic search, and schema parsing
XSD_TO_PYTHON: Dict[str, Type[Any]] = {
    "xsd:string": str,
    "xsd:decimal": float,
    "xsd:integer": int,
    "xsd:boolean": bool,
    "xsd:date": date,
    "xsd:dateTime": datetime,
    "xsd:datetime": datetime,  # Alternative casing
    "xsd:anyURI": str,
}

# Reverse mapping for serialization
PYTHON_TO_XSD: Dict[Type[Any], str] = {
    str: "xsd:string",
    float: "xsd:decimal",
    int: "xsd:integer",
    bool: "xsd:boolean",
    date: "xsd:date",
    datetime: "xsd:dateTime",
}


def python_type_for_xsd(xsd_type: str, default: Type[Any] = str) -> Type[Any]:
    """
    Get the Python type corresponding to an XSD type.

    Args:
        xsd_type: XSD type string (e.g., "xsd:string", "xsd:integer")
        default: Default type if XSD type is not recognized

    Returns:
        Corresponding Python type
    """
    return XSD_TO_PYTHON.get(xsd_type, default)


def xsd_type_for_python(py_type: Type[Any], default: str = "xsd:string") -> str:
    """
    Get the XSD type string for a Python type.

    Args:
        py_type: Python type
        default: Default XSD type if Python type is not recognized

    Returns:
        Corresponding XSD type string
    """
    return PYTHON_TO_XSD.get(py_type, default)
