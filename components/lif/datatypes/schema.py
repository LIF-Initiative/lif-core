from dataclasses import dataclass
from typing import Any, Dict

@dataclass
class SchemaField:
    """Represents a single schema field, including its path and attributes."""

    json_path: str
    description: str
    attributes: Dict[str, Any]
    py_field_name: str = ""
