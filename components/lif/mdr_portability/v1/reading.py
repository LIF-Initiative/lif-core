"""How format version 1 files are read: one Reader per file kind (see reader.py)."""

from typing import Any, Optional

from pydantic import BaseModel
from pydantic_core import ErrorDetails

from lif.mdr_portability.errors import PortabilityErrorCode
from lif.mdr_portability.reader import Location, Reader, get_nested
from lif.mdr_portability.v1.models import CHILD_KEY_TAGS, CrosswalkFile, MappingGroupFile, ModelFile

# Keys listed in §11, by the object they are deprecated on: the list or object a key sits in, or ""
# for the top level. Each follows the table that held the column (mdr_sql_model), so Type is
# deprecated on Details only, not on an entity. A key named Id or ending in Id is refused as a row ID
# first, so the many deprecated *Id columns need no entry here.
_EXTENSION = frozenset({"Extension", "ExtensionNotes"})

MODEL_DEPRECATED_KEYS = {
    "": frozenset({"DataModelConstraints", "ExtMappedValueSet"}),
    "Details": frozenset({"Type"}),
    "ValueSets": _EXTENSION,
    "Values": _EXTENSION,
    "Entities": _EXTENSION,
    "Attributes": _EXTENSION | {"Array", "Constraints"},
    "Associations": _EXTENSION | {"Placement", "Relationship"},
}
MAPPING_GROUP_DEPRECATED_KEYS = {
    "Details": _EXTENSION,
    "Mappings": _EXTENSION | {"InputAttributesCount", "OutputAttributesCount"},
    "Target": _EXTENSION,
    "Sources": _EXTENSION,
}
# The value-mapping table has no Extension column, so nothing in a crosswalk file is deprecated.
CROSSWALK_DEPRECATED_KEYS: dict[str, frozenset[str]] = {}

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
    # A mapping has exactly one target (§6.2). A null target counts as missing, as NULL does for
    # every required field (§10), and so does an empty list. A list of one is a single target in the
    # wrong shape, so it falls through to FIELD_INVALID.
    if len(location) == 3 and location[0] == "Mappings" and location[2] == "Target":
        target = error["input"]
        if error["type"] == "missing" or target is None or target == []:
            return PortabilityErrorCode.MAPPING_TARGET_MISSING
        if isinstance(target, list) and len(target) > 1:
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


def _reader(
    file_class: type[BaseModel],
    deprecated_keys: dict[str, frozenset[str]],
    model_identity_locations: frozenset[Location],
) -> Reader:
    return Reader(
        file_class=file_class,
        deprecated_keys=deprecated_keys,
        model_identity_locations=model_identity_locations,
        list_item_keys=LIST_ITEM_KEYS,
        union_tags=frozenset(("Child", tag) for tag in CHILD_KEY_TAGS),
        location_specific_code=_location_specific_code,
    )


MODEL_READER = _reader(
    ModelFile, MODEL_DEPRECATED_KEYS, _model_identity_locations(("Details",), ("Details", "CopiedFrom"))
)
MAPPING_GROUP_READER = _reader(
    MappingGroupFile,
    MAPPING_GROUP_DEPRECATED_KEYS,
    _model_identity_locations(("Details", "Source"), ("Details", "Target")),
)
CROSSWALK_READER = _reader(
    CrosswalkFile,
    CROSSWALK_DEPRECATED_KEYS,
    _model_identity_locations(("Details", "Source", "Model"), ("Details", "Target", "Model")),
)
