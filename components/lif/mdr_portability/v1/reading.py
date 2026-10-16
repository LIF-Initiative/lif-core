"""How format version 1 files are read: one Reader per file kind (see reader.py)."""

from typing import Any, Optional

from pydantic import BaseModel
from pydantic_core import ErrorDetails

from lif.mdr_portability.errors import PortabilityErrorCode
from lif.mdr_portability.reader import Location, Reader, get_nested
from lif.mdr_portability.v1.models import CHILD_KEY_TAGS, CrosswalkFile, MappingGroupFile, ModelFile

# Keys listed in §11. A key named Id or ending in Id is refused as a row ID first, so the many
# deprecated *Id columns need no entry here. Array is deprecated on entities and attributes only;
# on an association it is a defined key and never reaches this check.
DEPRECATED_KEYS = frozenset(
    {
        "Array",
        "Constraints",
        "DataModelConstraints",
        "ExtMappedValueSet",
        "Extension",
        "ExtensionNotes",
        "InputAttributesCount",
        "OutputAttributesCount",
        "Placement",
        "Relationship",
        "Type",
    }
)

MODEL_IDENTITY_FIELDS = frozenset({"Name", "Version", "ContributorOrganization"})


def _association_key(item: Any) -> Optional[str]:
    parent = get_nested(item, "Parent", "Entity")
    name = get_nested(item, "Name")
    return f"{parent}, {name}" if isinstance(parent, str) and isinstance(name, str) else None


# How an item in each list is named in an error, by its key (§4.3, §9).
LIST_ITEM_KEYS = {
    "ValueSets": lambda item: get_nested(item, "Name"),
    "Values": lambda item: get_nested(item, "ValueName"),
    "Entities": lambda item: get_nested(item, "UniqueName"),
    "Attributes": lambda item: get_nested(item, "UniqueName"),
    "Associations": _association_key,
    "Mappings": lambda item: get_nested(item, "Target", "Path"),
    "Sources": lambda item: get_nested(item, "Path"),
    "Entries": lambda item: get_nested(item, "Source"),
}


def _location_specific_code(error: ErrorDetails, location: Location) -> Optional[PortabilityErrorCode]:
    if error["type"] == "literal_error" and location[-1] == "ExpressionLanguage":
        return PortabilityErrorCode.EXPRESSION_LANGUAGE_NOT_PORTABLE
    # A mapping has exactly one target (§6.2).
    if len(location) == 3 and location[0] == "Mappings" and location[2] == "Target":
        if error["type"] == "missing":
            return PortabilityErrorCode.MAPPING_TARGET_MISSING
        if isinstance(error["input"], list):
            return PortabilityErrorCode.MAPPING_TARGET_MULTIPLE
    return None


def _model_identity_locations(*identity_objects: Location) -> frozenset[Location]:
    # For ("Details", "CopiedFrom"): the object itself, for when it is missing or not an object, plus
    # ("Details", "CopiedFrom", "Name"), ("Details", "CopiedFrom", "Version") and
    # ("Details", "CopiedFrom", "ContributorOrganization"). The object's other fields, such as
    # Details.State, are not part of the identity.
    locations: set[Location] = set()
    for identity_object in identity_objects:
        locations.add(identity_object)
        for field in MODEL_IDENTITY_FIELDS:
            locations.add((*identity_object, field))
    return frozenset(locations)


def _reader(file_class: type[BaseModel], model_identity_locations: frozenset[Location]) -> Reader:
    return Reader(
        file_class=file_class,
        deprecated_keys=DEPRECATED_KEYS,
        model_identity_locations=model_identity_locations,
        list_item_keys=LIST_ITEM_KEYS,
        union_tags=CHILD_KEY_TAGS,
        location_specific_code=_location_specific_code,
    )


MODEL_READER = _reader(ModelFile, _model_identity_locations(("Details",), ("Details", "CopiedFrom")))
MAPPING_GROUP_READER = _reader(
    MappingGroupFile, _model_identity_locations(("Details", "Source"), ("Details", "Target"))
)
CROSSWALK_READER = _reader(
    CrosswalkFile, _model_identity_locations(("Details", "Source", "Model"), ("Details", "Target", "Model"))
)
