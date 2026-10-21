"""Check the rules of a model file that span elements, refusing with the codes in Portability Spec §10.

parse_model_file checks each object on its own; these rules compare elements with each other. They
take a ModelFile rather than bytes, because import is also handed models that were never parsed, such
as a clone's (§8). Every rule is checked, and all the errors are raised together, as one
PortabilityErrorGroup.

Keys are compared exactly as written, as the database's unique indexes compare them (§4.3).
"""

from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass

from lif.mdr_portability.errors import PortabilityError, PortabilityErrorCode, error_group
from lif.mdr_portability.v1.models import Association, AttributeKey, EntityKey, ModelFile


def check_model_file(file: ModelFile) -> None:
    errors = [
        *_check_for_duplicate_keys(file),
        *_check_for_unresolved_element_references(file),
        *_check_for_reference_flag_on_attribute_child(file),
        *_check_for_duplicate_association_names(file),
        *_check_for_containment_cycles(file),
        *_check_for_unassociated_attributes(file),
    ]
    if errors:
        raise error_group(errors)


def _check_for_duplicate_keys(file: ModelFile) -> Iterator[PortabilityError]:
    # Keys are unique per kind (§4.3), so an entity and an attribute may share a UniqueName.
    yield from _check_list_for_duplicate_keys("ValueSets", [value_set.Name for value_set in file.ValueSets])
    yield from _check_list_for_duplicate_keys("Entities", [entity.UniqueName for entity in file.Entities])
    yield from _check_list_for_duplicate_keys("Attributes", [attribute.UniqueName for attribute in file.Attributes])
    # A value's key is unique within its value set.
    for value_set in file.ValueSets:
        values_path = f"ValueSets[{value_set.Name}].Values"
        yield from _check_list_for_duplicate_keys(values_path, [value.ValueName for value in value_set.Values])


def _check_list_for_duplicate_keys(list_path: str, keys: list[str]) -> Iterator[PortabilityError]:
    for key, count in Counter(keys).items():
        if count > 1:
            yield PortabilityError(
                PortabilityErrorCode.DUPLICATE_KEY, f"{list_path}[{key}]", f"{count} items share the key {key!r}"
            )


def _check_for_unresolved_element_references(file: ModelFile) -> Iterator[PortabilityError]:
    # An element reference, such as { "Entity": "Course" }, names an element by its key (§4.3). It is not
    # an association's Reference flag (§5.4). It resolves only to an element of its own kind, so
    # { "Attribute": "Course" } does not resolve to an entity named Course.
    keys_by_kind = {
        "value set": {value_set.Name for value_set in file.ValueSets},
        "entity": {entity.UniqueName for entity in file.Entities},
        "attribute": {attribute.UniqueName for attribute in file.Attributes},
    }
    for element, kind, key in _list_element_references(file):
        if key not in keys_by_kind[kind]:
            yield PortabilityError(
                PortabilityErrorCode.ELEMENT_REFERENCE_UNRESOLVED, element, f"no {kind} has the key {key!r}"
            )


def _list_element_references(file: ModelFile) -> Iterator[tuple[str, str, str]]:
    # Every element reference in the file: where it is, the kind of element it names, and that element's key.
    for attribute in file.Attributes:
        if attribute.ValueSet:
            yield f"Attributes[{attribute.UniqueName}].ValueSet", "value set", attribute.ValueSet.ValueSet
    for association in file.Associations:
        association_path = _get_association_path(association)
        yield f"{association_path}.Parent", "entity", association.Parent.Entity
        child = association.Child
        if isinstance(child, EntityKey):
            yield f"{association_path}.Child", "entity", child.Entity
        else:
            yield f"{association_path}.Child", "attribute", child.Attribute


def _check_for_reference_flag_on_attribute_child(file: ModelFile) -> Iterator[PortabilityError]:
    # Only an entity exists in its own right, so only an entity child can be referenced rather than
    # contained (§5.4).
    for association in file.Associations:
        if association.Reference and isinstance(association.Child, AttributeKey):
            yield PortabilityError(
                PortabilityErrorCode.REFERENCE_INVALID,
                f"{_get_association_path(association)}.Reference",
                "Reference is allowed only when the child is an entity, and this child is an attribute",
            )


def _check_for_duplicate_association_names(file: ModelFile) -> Iterator[PortabilityError]:
    # A parent has at most one child under a given Name (§5.4). The same child may appear under one
    # parent more than once, under different names: that is how roles are expressed.
    paths = Counter(_get_association_path(association) for association in file.Associations)
    for association_path, count in paths.items():
        if count > 1:
            yield PortabilityError(
                PortabilityErrorCode.ASSOCIATION_NAME_TAKEN,
                association_path,
                f"{count} associations have this parent and Name",
            )


def _check_for_containment_cycles(file: ModelFile) -> Iterator[PortabilityError]:
    # The containing associations, those without Reference, must form no cycle (§5.4). A cycle that
    # passes through a reference is allowed: it is how recursion is expressed.
    for association, cycle in _find_containment_cycles(_get_contained_children(file)):
        # A plain list, which reads the same in a log and through a screen reader. It starts and ends with
        # the same entity: 'Person', 'Person.Contact', 'Person'.
        yield PortabilityError(
            PortabilityErrorCode.ASSOCIATION_CYCLE,
            _get_association_path(association),
            f"a cycle of containing associations: {', '.join(map(repr, cycle))}",
        )


def _get_contained_children(file: ModelFile) -> dict[str, list[tuple[Association, str]]]:
    # Each entity's contained entity children, with the association that contains each one. An end that
    # does not resolve is refused as ELEMENT_REFERENCE_UNRESOLVED, and is left out here.
    contained_children: dict[str, list[tuple[Association, str]]] = {entity.UniqueName: [] for entity in file.Entities}
    for association in file.Associations:
        parent, child = association.Parent.Entity, association.Child
        if (
            isinstance(child, EntityKey)
            and not association.Reference
            and parent in contained_children
            and child.Entity in contained_children
        ):
            contained_children[parent].append((association, child.Entity))
    return contained_children


@dataclass
class _EntityOnPath:
    # One entity on the walk's current path, with the children it has not walked yet.
    entity: str
    children_left_to_walk: Iterator[tuple[Association, str]]


def _find_containment_cycles(
    contained_children: dict[str, list[tuple[Association, str]]],
) -> Iterator[tuple[Association, list[str]]]:
    # Walk depth-first from each entity, visiting each entity once (§8). Reaching an entity on the
    # current path is a cycle; reaching one already walked is a shared entity, such as Identifier under
    # both Organization and Person. Yields the association that closes each cycle, and the entities on it.
    #
    # The path is kept as a list rather than as recursion, because containment may nest thousands of
    # levels deep. Each step either goes down into the next child of the last entity on the path, or,
    # when that entity has no children left, steps back up to its parent.
    walked_entities: set[str] = set()
    for start_entity in contained_children:
        if start_entity in walked_entities:
            continue
        entity_path = [_EntityOnPath(start_entity, iter(contained_children[start_entity]))]
        while entity_path:
            next_child = next(entity_path[-1].children_left_to_walk, None)
            if next_child is None:
                # Step back up: every child of the last entity on the path has been walked.
                walked_entities.add(entity_path.pop().entity)
                continue
            association, child_entity = next_child
            entity_names_on_path = [path_entry.entity for path_entry in entity_path]
            if child_entity in entity_names_on_path:
                cycle_start = entity_names_on_path.index(child_entity)
                yield association, [*entity_names_on_path[cycle_start:], child_entity]
            elif child_entity not in walked_entities:
                # Go down into the child.
                entity_path.append(_EntityOnPath(child_entity, iter(contained_children[child_entity])))


def _check_for_unassociated_attributes(file: ModelFile) -> Iterator[PortabilityError]:
    # Every attribute must be the child of at least one association, because an attribute with none
    # has no place in the generated schema (§5.3). An association whose parent does not resolve still
    # places its child: it is refused as ELEMENT_REFERENCE_UNRESOLVED instead.
    associated_attribute_names = {
        association.Child.Attribute for association in file.Associations if isinstance(association.Child, AttributeKey)
    }
    for attribute in file.Attributes:
        if attribute.UniqueName not in associated_attribute_names:
            yield PortabilityError(
                PortabilityErrorCode.UNASSOCIATED_ATTRIBUTE,
                f"Attributes[{attribute.UniqueName}]",
                "the attribute is the child of no association, so it has no place in the generated schema",
            )


def _get_association_path(association: Association) -> str:
    # An association is named by its key, its parent and Name, as in Associations[Course, AccreditedBy].
    return f"Associations[{association.Parent.Entity}, {association.Name}]"
