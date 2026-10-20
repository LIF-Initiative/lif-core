"""Read a portable file into its model, refusing with the codes in Portability Spec §10.

The envelope is checked first (§4.1, §4.2): a file that is not JSON, has no Format, or is another
kind of file is refused before anything else is read. The file's (Format.Type, Format.Version) then
picks the Reader that knows that version (_READERS); the rest is validated by its model, and every
validation error becomes a PortabilityError. All of them are raised together, as one
PortabilityErrorGroup.

These steps are the same for every version. What differs between versions lives in that version's
package, such as v1/reading.py.

Rules that span elements (keys, references, cycles, paths) are not checked here.
"""

import json
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError
from pydantic_core import ErrorDetails

from lif.mdr_portability.errors import PortabilityError, PortabilityErrorCode, PortabilityErrorGroup
from lif.mdr_portability.reader import Location, Reader
from lif.mdr_portability.v1 import reading as v1
from lif.mdr_portability.v1.models import CrosswalkFile, MappingGroupFile, ModelFile

FileModel = TypeVar("FileModel", bound=BaseModel)

# (Format.Type, Format.Version) -> the Reader for that version of that file kind. A new format version
# adds a row per file kind, plus a step that upgrades the previous version's model to it (§4.2), so
# the parse_* functions always return the current version.
_READERS: dict[tuple[str, int], Reader] = {
    ("lif-mdr-model", 1): v1.MODEL_READER,
    ("lif-mdr-mapping-group", 1): v1.MAPPING_GROUP_READER,
    ("lif-mdr-crosswalk", 1): v1.CROSSWALK_READER,
}


def parse_model_file(text: str | bytes) -> ModelFile:
    return _parse(text, "lif-mdr-model", ModelFile)


def parse_mapping_group_file(text: str | bytes) -> MappingGroupFile:
    return _parse(text, "lif-mdr-mapping-group", MappingGroupFile)


def parse_crosswalk_file(text: str | bytes) -> CrosswalkFile:
    return _parse(text, "lif-mdr-crosswalk", CrosswalkFile)


def _group(errors: list[PortabilityError]) -> PortabilityErrorGroup:
    # The message is only for logs and tracebacks; callers read the errors themselves.
    return PortabilityErrorGroup(f"{len(errors)} portability error{'s' if len(errors) != 1 else ''}", errors)


def _refuse(code: PortabilityErrorCode, element: str, reason: str) -> PortabilityErrorGroup:
    return _group([PortabilityError(code, element, reason)])


def _get_reader_for(data: Any, format_type: str) -> Reader:
    if not isinstance(data, dict) or not isinstance(data.get("Format"), dict):
        raise _refuse(PortabilityErrorCode.FORMAT_UNKNOWN, "Format", "the file has no Format object")
    found_type = data["Format"].get("Type")
    if found_type != format_type:
        raise _refuse(
            PortabilityErrorCode.FORMAT_UNKNOWN, "Format.Type", f"expected {format_type!r}, found {found_type!r}"
        )
    version = data["Format"].get("Version")
    # type() rather than ==, because True == 1 and 1.0 == 1.
    reader = _READERS.get((format_type, version)) if type(version) is int else None
    if reader is None:
        supported = sorted(read_version for read_type, read_version in _READERS if read_type == format_type)
        raise _refuse(
            PortabilityErrorCode.FORMAT_VERSION_UNSUPPORTED,
            "Format.Version",
            f"this converter reads version {', '.join(map(str, supported))} of {format_type}, found {version!r}",
        )
    return reader


class _RepeatedKeyError(Exception):
    def __init__(self, key: str):
        super().__init__(key)
        self.key = key


def _refuse_repeated_keys(pairs: list[tuple[str, Any]]) -> dict:
    # Called by json.loads for each JSON object. JSON parsers disagree on which of two repeated keys
    # wins, so a repeated key is refused rather than one of its values kept silently (§4.2).
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise _RepeatedKeyError(key)
        result[key] = value
    return result


def _parse(text: str | bytes, format_type: str, current: type[FileModel]) -> FileModel:
    # A leading byte order mark is accepted (§9). json.loads already drops one from bytes but refuses
    # one in text, so text read without "utf-8-sig" would otherwise fail where the same bytes pass.
    if isinstance(text, str):
        text = text.removeprefix("\N{BYTE ORDER MARK}")
    try:
        data = json.loads(text, object_pairs_hook=_refuse_repeated_keys)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise _refuse(PortabilityErrorCode.FORMAT_UNKNOWN, "", f"not JSON: {error}") from None
    except _RepeatedKeyError as error:
        raise _refuse(
            PortabilityErrorCode.FIELD_INVALID, error.key, f"the key {error.key!r} appears more than once in one object"
        ) from None
    reader = _get_reader_for(data, format_type)
    try:
        file = reader.file_class.model_validate(data)
    except ValidationError as validation_error:
        raise _group([_to_portability_error(error, data, reader) for error in validation_error.errors()]) from None
    # An older version's file would be upgraded here, one version at a time. Only version 1 exists,
    # so its model is the current one. A reader added without its upgrade step fails here.
    if not isinstance(file, current):
        raise TypeError(f"no upgrade from {_qualified_name(type(file))} to {_qualified_name(current)}")
    return file


def _qualified_name(model: type) -> str:
    # Includes the version package, such as lif.mdr_portability.v1.models.ModelFile.
    return f"{model.__module__}.{model.__qualname__}"


def _without_union_tags(location: Location, reader: Reader) -> Location:
    # Drop a segment only when it is a tag right after its union's field. Elsewhere the same text is
    # a real key, such as an unknown key that happens to be named EntityKey. zip pairs each segment
    # with the one before it.
    return tuple(
        segment
        for previous, segment in zip((None, *location), location)
        if (previous, segment) not in reader.union_tags
    )


def _to_portability_error(error: ErrorDetails, data: Any, reader: Reader) -> PortabilityError:
    location = _without_union_tags(error["loc"], reader)
    return PortabilityError(
        _choose_error_code(error, location, reader), _generate_element_path(location, data, reader), error["msg"]
    )


def _choose_error_code(error: ErrorDetails, location: Location, reader: Reader) -> PortabilityErrorCode:
    if error["type"] == "extra_forbidden":
        key = str(location[-1])
        # No row IDs, in any version (§3).
        if key == "Id" or key.endswith("Id"):
            return PortabilityErrorCode.ROW_ID_PRESENT
        if key in reader.deprecated_keys:
            return PortabilityErrorCode.DEPRECATED_FIELD
        return PortabilityErrorCode.FIELD_UNKNOWN
    if location in reader.model_identity_locations:
        return PortabilityErrorCode.MODEL_IDENTITY_INCOMPLETE
    return reader.location_specific_code(error, location) or PortabilityErrorCode.FIELD_INVALID


def _generate_element_path(location: Location, data: Any, reader: Reader) -> str:
    # Render a location as a path, naming list items by their key where they have one, as in
    # Portability Spec §12.3's `Entities[Assessment].Id`.
    parts: list[str] = []
    node = data
    list_name = None
    for segment in location:
        if isinstance(segment, int):
            # The segment is a list index, such as 0 in ("Entities", 0, "Id").
            # The item at that index in the file's list, or None if there is no list or no such item.
            item = node[segment] if isinstance(node, list) and segment < len(node) else None
            # The function that reads this list's key from an item, such as UniqueName for Entities.
            item_key = reader.list_item_keys.get(list_name) if list_name else None
            # The item's key, such as "Competency", if the list has a key and the item is an object.
            key = item_key(item) if item_key and isinstance(item, dict) else None
            # Name the item by its key ("Entities[Competency]"), or by its index ("Entities[0]") when the
            # key is missing, not a string, or blank.
            parts[-1] += f"[{key}]" if isinstance(key, str) and key.strip() else f"[{segment}]"
            # Continue from the item, for the segments that follow it.
            node = item
        else:
            parts.append(segment)
            list_name = segment
            node = node.get(segment) if isinstance(node, dict) else None
    return ".".join(parts)
