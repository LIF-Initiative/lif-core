from enum import Enum


class PortabilityErrorCode(str, Enum):
    """Named refusals from the portable file format spec (docs/specs/mdr-portable-file-format.md §10)."""

    FORMAT_UNKNOWN = "FORMAT_UNKNOWN"
    FORMAT_VERSION_UNSUPPORTED = "FORMAT_VERSION_UNSUPPORTED"
    FIELD_UNKNOWN = "FIELD_UNKNOWN"
    FIELD_INVALID = "FIELD_INVALID"
    DEPRECATED_FIELD = "DEPRECATED_FIELD"
    ROW_ID_PRESENT = "ROW_ID_PRESENT"
    MODEL_IDENTITY_INCOMPLETE = "MODEL_IDENTITY_INCOMPLETE"
    MODEL_EXISTS = "MODEL_EXISTS"
    GROUP_EXISTS = "GROUP_EXISTS"
    CROSSWALK_EXISTS = "CROSSWALK_EXISTS"
    MODEL_MISSING = "MODEL_MISSING"
    ASSOCIATION_CYCLE = "ASSOCIATION_CYCLE"
    REFERENCE_INVALID = "REFERENCE_INVALID"
    ELEMENT_REFERENCE_UNRESOLVED = "ELEMENT_REFERENCE_UNRESOLVED"
    DUPLICATE_KEY = "DUPLICATE_KEY"
    ASSOCIATION_NAME_TAKEN = "ASSOCIATION_NAME_TAKEN"
    TOP_LEVEL_NAME_TAKEN = "TOP_LEVEL_NAME_TAKEN"
    UNASSOCIATED_ATTRIBUTE = "UNASSOCIATED_ATTRIBUTE"
    EXPRESSION_LANGUAGE_NOT_PORTABLE = "EXPRESSION_LANGUAGE_NOT_PORTABLE"
    MAPPING_TARGET_MISSING = "MAPPING_TARGET_MISSING"
    MAPPING_TARGET_MULTIPLE = "MAPPING_TARGET_MULTIPLE"
    MAPPING_TARGET_SHARED = "MAPPING_TARGET_SHARED"
    PATH_INVALID = "PATH_INVALID"
    CROSSWALK_SOURCE_DUPLICATE = "CROSSWALK_SOURCE_DUPLICATE"
    NOT_MIGRATED = "NOT_MIGRATED"


class PortabilityError(Exception):
    """One refusal: its code, the element it concerns (by key or path), and why (spec §10)."""

    def __init__(self, code: PortabilityErrorCode, element: str, reason: str):
        super().__init__(f"{code.value} at {element or '(file)'}: {reason}")
        self.code = code
        self.element = element
        self.reason = reason


class PortabilityErrorGroup(ExceptionGroup[PortabilityError]):
    """Every refusal found in one file, so a caller can report them all at once."""


def error_group(errors: list[PortabilityError]) -> PortabilityErrorGroup:
    # The message is only for logs and tracebacks; callers read the errors themselves.
    return PortabilityErrorGroup(f"{len(errors)} portability error{'s' if len(errors) != 1 else ''}", errors)
