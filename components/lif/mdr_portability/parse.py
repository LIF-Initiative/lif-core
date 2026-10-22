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
from collections.abc import Callable
from typing import Any, Optional, TypeVar

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


# The parsers take the file's bytes, not text, because the encoding rules (UTF-8, an optional BOM,
# §9) are rules about bytes: a caller that decoded the file has already chosen its encoding.


def parse_model_file(content: bytes) -> ModelFile:
    return _parse(content, "lif-mdr-model", ModelFile)


def parse_mapping_group_file(content: bytes) -> MappingGroupFile:
    return _parse(content, "lif-mdr-mapping-group", MappingGroupFile)


def parse_crosswalk_file(content: bytes) -> CrosswalkFile:
    return _parse(content, "lif-mdr-crosswalk", CrosswalkFile)


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


def _has_text_utf8_cannot_encode(data: Any) -> bool:
    # True if any key or string holds a lone surrogate, which only a JSON escape such as \ud800 can
    # produce. UTF-8 cannot encode one, so the file could never be written out again (§9). An explicit
    # stack rather than recursion, because the data may be nested thousands of levels deep.
    stack = [data]
    while stack:
        node = stack.pop()
        if isinstance(node, str):
            try:
                node.encode("utf-8")
            except UnicodeEncodeError:
                return True
        elif isinstance(node, dict):
            stack.extend(node.keys())
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
        # Numbers, booleans and null hold no text, so there is nothing to check.
    return False


def _parse(content: bytes, format_type: str, current: type[FileModel]) -> FileModel:
    # Files are UTF-8 (§9). The bytes are decoded here rather than by json.loads, which would also
    # accept UTF-16 and UTF-32.
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise _refuse(PortabilityErrorCode.FORMAT_UNKNOWN, "", f"not UTF-8: {error}") from None
    # A leading byte order mark is accepted (§9).
    text = text.removeprefix("\N{BYTE ORDER MARK}")
    try:
        data = json.loads(text, object_pairs_hook=_refuse_repeated_keys)
    # ValueError covers malformed JSON (JSONDecodeError is a ValueError) and an integer too long for
    # Python to convert. RecursionError is nesting too deep to read. Every one is a refusal, never an
    # exception the caller has to know about.
    except (ValueError, RecursionError) as error:
        raise _refuse(PortabilityErrorCode.FORMAT_UNKNOWN, "", f"could not be read as JSON: {error}") from None
    except _RepeatedKeyError as error:
        raise _refuse(
            PortabilityErrorCode.FIELD_INVALID, error.key, f"the key {error.key!r} appears more than once in one object"
        ) from None
    reader = _get_reader_for(data, format_type)
    if _has_text_utf8_cannot_encode(data):
        raise _refuse(
            PortabilityErrorCode.FIELD_INVALID,
            "",
            "a string holds a lone surrogate (an unpaired escape such as \\ud800), which UTF-8 cannot encode",
        )
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


def _containing_object(location: Location) -> str:
    # The name of the list or object a key sits in, skipping list positions: "Entities" for
    # ("Entities", 0, "Type"), "Details" for ("Details", "Type"), and "" for a top-level key.
    return next((segment for segment in reversed(location[:-1]) if isinstance(segment, str)), "")


def _choose_error_code(error: ErrorDetails, location: Location, reader: Reader) -> PortabilityErrorCode:
    if error["type"] == "extra_forbidden":
        key = str(location[-1])
        # No row IDs, in any version (§3).
        if key == "Id" or key.endswith("Id"):
            return PortabilityErrorCode.ROW_ID_PRESENT
        if key in reader.deprecated_keys.get(_containing_object(location), frozenset()):
            return PortabilityErrorCode.DEPRECATED_FIELD
        return PortabilityErrorCode.FIELD_UNKNOWN
    if location in reader.model_identity_locations:
        return PortabilityErrorCode.MODEL_IDENTITY_INCOMPLETE
    return reader.location_specific_code(error, location) or PortabilityErrorCode.FIELD_INVALID


def _names_one_item(key: Any, items: list[Any], item_key: Callable[[Any], Optional[str]]) -> bool:
    # A key names one item when it is a non-blank string, holds no brackets that would make the path
    # unreadable (Entities[a]b]), and no other item in the same list has it. Two items sharing a key
    # are refused later (DUPLICATE_KEY); until then, an index is the only way to tell them apart.
    if not isinstance(key, str) or not key.strip():
        return False
    if "[" in key or "]" in key:
        return False
    keys_in_list = [item_key(other) for other in items if isinstance(other, dict)]
    return keys_in_list.count(key) == 1


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
            # Name the item by its key ("Entities[Competency]") when that names exactly one item, or by
            # its index ("Entities[0]") otherwise.
            named = isinstance(node, list) and item_key is not None and _names_one_item(key, node, item_key)
            parts[-1] += f"[{key}]" if named else f"[{segment}]"
            # Continue from the item, for the segments that follow it.
            node = item
        else:
            parts.append(segment)
            list_name = segment
            node = node.get(segment) if isinstance(node, dict) else None
    return ".".join(parts)
