"""Translate mapping paths between a file's association names and the database's EntityIdPath.

A file names a field by a top-level entity's UniqueName, then association Names, as in
`Course,AccreditedBy,name` (Portability Spec §6.3, ADR metadata_repository/0010). The database stores
the same field as an EntityIdPath, a chain of row IDs: entity IDs, then the attribute's ID negated, as
in `4,241,239,-1307` (transformation_service.parse_transformation_path).

Both directions work on a ModelPaths, an in-memory view of one installed model, so these rules need no
database. Each refusal is raised as one PortabilityError, naming the element the caller passes in.
"""

import re
from dataclasses import dataclass
from typing import NamedTuple, Optional

from lif.mdr_portability.errors import PortabilityError, PortabilityErrorCode

# A legacy segment that starts with a model's row ID, such as `1:Assessment` (§6.3).
_ROW_ID_SEGMENT = re.compile(r"^\d+:")


@dataclass(frozen=True)
class AssociationEnd:
    """One live association under a parent entity: its Name, and the child it leads to."""

    name: Optional[str]  # NULL until an MDR image that writes it, or V1.9, has filled it (#1386)
    child_id: int
    child_is_attribute: bool


@dataclass(frozen=True)
class ModelPaths:
    """What path translation needs from one installed model's live rows."""

    entity_names: dict[int, str]  # entity Id -> UniqueName
    attribute_names: dict[int, str]  # attribute Id -> UniqueName
    top_level_entity_ids: frozenset[int]  # entities with no containing parent (§6.3 rule 1)
    associations: dict[int, list[AssociationEnd]]  # parent entity Id -> its associations


class ResolvedPath(NamedTuple):
    """A file path resolved in an installed model, in the shape TransformationAttributes stores."""

    entity_id_path: str  # "4,241,239,-1307"
    entity_id: int  # the last entity, which holds the attribute
    attribute_id: int


def check_path_syntax(path: str, element: str) -> list[PortabilityError]:
    """The rules a path must meet before any model is consulted (§6.3)."""
    segments = path.split(",")
    errors = [
        PortabilityError(
            PortabilityErrorCode.ROW_ID_PRESENT,
            element,
            f"segment {segment!r} starts with a row ID; name the element instead",
        )
        for segment in segments
        if _ROW_ID_SEGMENT.match(segment)
    ]
    if any(not segment.strip() for segment in segments):
        errors.append(PortabilityError(PortabilityErrorCode.PATH_INVALID, element, "a segment is empty"))
    elif len(segments) < 2:
        errors.append(
            PortabilityError(
                PortabilityErrorCode.PATH_INVALID,
                element,
                "a path names a top-level entity and then at least one association, ending at an attribute",
            )
        )
    return errors


def to_entity_id_path(path: str, model: ModelPaths, element: str) -> ResolvedPath:
    """Resolve a file path in an installed model (import)."""
    syntax_errors = check_path_syntax(path, element)
    if syntax_errors:
        raise syntax_errors[0]

    first, *rest = path.split(",")
    top_level = [entity_id for entity_id in model.top_level_entity_ids if model.entity_names[entity_id] == first]
    if len(top_level) != 1:
        reason = "no top-level entity has" if not top_level else f"{len(top_level)} top-level entities have"
        raise PortabilityError(PortabilityErrorCode.PATH_INVALID, element, f"{reason} the UniqueName {first!r}")

    ids = [top_level[0]]
    for position, segment in enumerate(rest):
        parent_id = ids[-1]
        parent = model.entity_names[parent_id]
        ends = [end for end in model.associations.get(parent_id, []) if end.name == segment]
        if len(ends) != 1:
            reason = "has no association named" if not ends else f"has {len(ends)} associations named"
            raise PortabilityError(PortabilityErrorCode.PATH_INVALID, element, f"{parent!r} {reason} {segment!r}")
        end = ends[0]
        is_last = position == len(rest) - 1
        if end.child_is_attribute and not is_last:
            raise PortabilityError(
                PortabilityErrorCode.PATH_INVALID, element, f"{segment!r} is an attribute, so it must be last"
            )
        if not end.child_is_attribute and is_last:
            raise PortabilityError(
                PortabilityErrorCode.PATH_INVALID, element, f"{segment!r} is an entity; a path ends at an attribute"
            )
        same_child = [
            other
            for other in model.associations.get(parent_id, [])
            if other.child_id == end.child_id and other.child_is_attribute == end.child_is_attribute
        ]
        if len(same_child) > 1:
            # Two roles store the same EntityIdPath, which export refuses (to_file_path), so refuse here too.
            child = (model.attribute_names if end.child_is_attribute else model.entity_names)[end.child_id]
            names = ", ".join(repr(other.name) for other in same_child)
            raise PortabilityError(
                PortabilityErrorCode.PATH_INVALID,
                element,
                f"the path cannot be stored unambiguously: {parent!r} reaches {child!r} by {len(same_child)} "
                f"associations ({names})",
            )
        ids.append(end.child_id)

    *entity_ids, attribute_id = ids
    return ResolvedPath(
        entity_id_path=",".join([*map(str, entity_ids), str(-attribute_id)]),
        entity_id=entity_ids[-1],
        attribute_id=attribute_id,
    )


def to_file_path(entity_id_path: str, model: ModelPaths, element: str) -> str:
    """Name a stored EntityIdPath by association names (export)."""
    try:
        ids = [int(segment) for segment in entity_id_path.split(",")]
    except ValueError:
        raise PortabilityError(
            PortabilityErrorCode.PATH_INVALID, element, f"the stored path {entity_id_path!r} is not a list of IDs"
        ) from None
    *entity_ids, attribute_id = ids
    if not entity_ids or attribute_id >= 0 or any(entity_id <= 0 for entity_id in entity_ids):
        raise PortabilityError(
            PortabilityErrorCode.PATH_INVALID,
            element,
            f"the stored path {entity_id_path!r} is not entities followed by one attribute",
        )

    first_id = entity_ids[0]
    if first_id not in model.entity_names:
        raise PortabilityError(
            PortabilityErrorCode.PATH_INVALID, element, f"entity {first_id} is not a live entity of the model"
        )
    if first_id not in model.top_level_entity_ids:
        raise PortabilityError(
            PortabilityErrorCode.PATH_INVALID,
            element,
            f"{model.entity_names[first_id]!r} is not a top-level entity, so it cannot start a path",
        )

    segments = [model.entity_names[first_id]]
    steps = [(child_id, False) for child_id in entity_ids[1:]] + [(-attribute_id, True)]
    parent_id = first_id
    for child_id, child_is_attribute in steps:
        ends = [
            end
            for end in model.associations.get(parent_id, [])
            if end.child_id == child_id and end.child_is_attribute == child_is_attribute
        ]
        parent = model.entity_names[parent_id]
        child = (model.attribute_names if child_is_attribute else model.entity_names).get(child_id, str(child_id))
        if not ends:
            raise PortabilityError(
                PortabilityErrorCode.PATH_INVALID, element, f"no live association leads from {parent!r} to {child!r}"
            )
        if len(ends) > 1:
            # Two roles, such as AccreditedBy and ApprovedBy, that an EntityIdPath cannot tell apart.
            names = ", ".join(repr(end.name) for end in ends)
            raise PortabilityError(
                PortabilityErrorCode.PATH_INVALID,
                element,
                f"the stored path is ambiguous: {parent!r} reaches {child!r} by {len(ends)} associations ({names})",
            )
        if ends[0].name is None:
            raise PortabilityError(
                PortabilityErrorCode.PATH_INVALID,
                element,
                f"the association from {parent!r} to {child!r} has no Name yet",
            )
        segments.append(ends[0].name)
        parent_id = child_id

    return ",".join(segments)
