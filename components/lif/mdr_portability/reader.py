"""What the parser needs to know about one version of one file kind.

Each format version defines a Reader per file kind in its own package (v1/reading.py), and parse.py
looks the Reader up by the file's (Format.Type, Format.Version). The parsing steps themselves are the
same for every version.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Optional

from pydantic import BaseModel
from pydantic_core import ErrorDetails

from lif.mdr_portability.errors import PortabilityErrorCode

Location = tuple[str | int, ...]


@dataclass(frozen=True)
class Reader:
    # The model this version's files are validated against.
    file_class: type[BaseModel]
    # Keys this version lists as deprecated (§11), refused with DEPRECATED_FIELD.
    deprecated_keys: frozenset[str]
    # Every location of a model identity (§2): each object holding one, and each of its identity
    # fields. An error at one of them is refused with MODEL_IDENTITY_INCOMPLETE.
    model_identity_locations: frozenset[Location]
    # How an item in each list is named in an error: list name -> the item's key, or None.
    list_item_keys: Mapping[str, Callable[[Any], Optional[str]]]
    # Tags Pydantic adds to an error's location inside a tagged union; left out of element paths.
    union_tags: frozenset[str]
    # Codes that depend on where in this version's files an error is; None when none applies.
    location_specific_code: Callable[[ErrorDetails, Location], Optional[PortabilityErrorCode]]


def get_nested(node: Any, *keys: str) -> Any:
    # Look up a nested value: get_nested(item, "Target", "Path") is item["Target"]["Path"]. This reads
    # the raw file to name the element in an error, and that file may be malformed (a Target that is a
    # list, a missing Parent), so it returns None rather than raising when a level is missing or not an
    # object.
    for key in keys:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node
