"""Check the rules of a model file that span elements, refusing with the codes in Portability Spec §10.

parse_model_file checks each object on its own; these rules compare elements with each other. They
take a ModelFile rather than bytes, because import is also handed models that were never parsed, such
as a clone's (§8). Every rule is checked, and all the errors are raised together, as one
PortabilityErrorGroup.

Keys are compared exactly as written, as the database's unique indexes compare them (§4.3).
"""

from collections.abc import Iterable, Iterator

from lif.mdr_portability.errors import PortabilityError, PortabilityErrorCode, error_group
from lif.mdr_portability.v1.models import Association, AttributeKey, EntityKey, ModelFile


def check_model_file(file: ModelFile) -> None:
    errors = [
        *_check_for_duplicate_keys(file),
        *_check_for_unresolved_element_references(file),
        *_check_for_reference_flag_on_attribute_child(file),
        *_check_for_duplicate_association_names(file),
        *_check_for_duplicate_top_level_names(file),
        *_check_for_array_on_entities_with_a_parent(file),
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
    for position, value_set in enumerate(file.ValueSets):
        values_path = f"{_get_item_path('ValueSets', value_set.Name, position)}.Values"
        yield from _check_list_for_duplicate_keys(values_path, [value.ValueName for value in value_set.Values])


def _check_list_for_duplicate_keys(list_path: str, keys: list[str]) -> Iterator[PortabilityError]:
    for key, (count, first_position) in _count_keys(keys).items():
        if count > 1:
            yield PortabilityError(
                PortabilityErrorCode.DUPLICATE_KEY,
                _get_item_path(list_path, key, first_position),
                f"{count} items share the key {key!r}",
            )


def _count_keys(keys: Iterable[str]) -> dict[str, tuple[int, int]]:
    # Each key, with how many items hold it and the position of the first, in the order keys first appear.
    counts: dict[str, tuple[int, int]] = {}
    for position, key in enumerate(keys):
        count, first_position = counts.get(key, (0, position))
        counts[key] = (count + 1, first_position)
    return counts


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
    for position, attribute in enumerate(file.Attributes):
        if attribute.ValueSet:
            attribute_path = _get_item_path("Attributes", attribute.UniqueName, position)
            yield f"{attribute_path}.ValueSet", "value set", attribute.ValueSet.ValueSet
    for position, association in enumerate(file.Associations):
        association_path = _get_association_path(association, position)
        yield f"{association_path}.Parent", "entity", association.Parent.Entity
        child = association.Child
        if isinstance(child, EntityKey):
            yield f"{association_path}.Child", "entity", child.Entity
        else:
            yield f"{association_path}.Child", "attribute", child.Attribute


def _check_for_reference_flag_on_attribute_child(file: ModelFile) -> Iterator[PortabilityError]:
    # Only an entity exists in its own right, so only an entity child can be referenced rather than
    # contained (§5.4).
    for position, association in enumerate(file.Associations):
        if association.Reference and isinstance(association.Child, AttributeKey):
            yield PortabilityError(
                PortabilityErrorCode.REFERENCE_INVALID,
                f"{_get_association_path(association, position)}.Reference",
                "Reference is allowed only when the child is an entity, and this child is an attribute",
            )


def _check_for_duplicate_association_names(file: ModelFile) -> Iterator[PortabilityError]:
    # A parent has at most one child under a given Name (§5.4). The same child may appear under one
    # parent more than once, under different names: that is how roles are expressed.
    association_keys = [_get_association_key(association) for association in file.Associations]
    for key, (count, first_position) in _count_keys(association_keys).items():
        if count > 1:
            yield PortabilityError(
                PortabilityErrorCode.ASSOCIATION_NAME_TAKEN,
                _get_item_path("Associations", key, first_position),
                f"{count} associations have this parent and Name",
            )


def _check_for_duplicate_top_level_names(file: ModelFile) -> Iterator[PortabilityError]:
    # An entity that is the child of no containing association has no parent, so it appears at the top
    # level of the generated schema under its Name, which is not its key (§5.3). Two such entities with
    # the same Name would appear under the same key. A reference does not give its child a parent: the
    # child exists in its own right (§5.4). Entities with the same UniqueName are refused as
    # DUPLICATE_KEY, so each UniqueName is counted once here.
    contained_entity_names = _get_contained_entity_names(file)
    # For each Name, the entities with no parent that have it: UniqueName -> position of the first.
    top_level_entities_by_name: dict[str, dict[str, int]] = {}
    for position, entity in enumerate(file.Entities):
        if entity.UniqueName not in contained_entity_names:
            positions = top_level_entities_by_name.setdefault(entity.Name, {})
            positions.setdefault(entity.UniqueName, position)
    for name, positions in top_level_entities_by_name.items():
        if len(positions) > 1:
            first_unique_name, first_position = next(iter(positions.items()))
            yield PortabilityError(
                PortabilityErrorCode.TOP_LEVEL_NAME_TAKEN,
                _get_item_path("Entities", first_unique_name, first_position),
                f"{len(positions)} entities with no parent have the Name {name!r}: {', '.join(map(repr, positions))}",
            )


def _check_for_array_on_entities_with_a_parent(file: ModelFile) -> Iterator[PortabilityError]:
    # An entity's own Array is for its top-level schema. An entity with a parent takes its list setting
    # from each association instead (§5.3, §5.4), so its own would mean nothing.
    contained_entity_names = _get_contained_entity_names(file)
    for position, entity in enumerate(file.Entities):
        if entity.Array and entity.UniqueName in contained_entity_names:
            yield PortabilityError(
                PortabilityErrorCode.FIELD_INVALID,
                f"{_get_item_path('Entities', entity.UniqueName, position)}.Array",
                "Array is allowed only on an entity with no parent; set it on the entity's associations instead",
            )


def _get_contained_entity_names(file: ModelFile) -> set[str]:
    # The entities that are the child of a containing association (§5.4).
    return {
        association.Child.Entity
        for association in file.Associations
        if isinstance(association.Child, EntityKey) and not association.Reference
    }


def _check_for_containment_cycles(file: ModelFile) -> Iterator[PortabilityError]:
    # The containing associations, those without Reference, must form no cycle (§5.4). A cycle that
    # passes through a reference is allowed: it is how recursion is expressed.
    for position, cycle in _find_containment_cycles(_get_contained_children(file)):
        # A plain list, which reads the same in a log and through a screen reader. It starts and ends with
        # the same entity: 'Person', 'Person.Contact', 'Person'.
        yield PortabilityError(
            PortabilityErrorCode.ASSOCIATION_CYCLE,
            _get_association_path(file.Associations[position], position),
            f"a cycle of containing associations: {', '.join(map(repr, cycle))}",
        )


def _get_contained_children(file: ModelFile) -> dict[str, list[tuple[int, str]]]:
    # Each entity's contained entity children, with the position of the association that contains each
    # one. An end that does not resolve is refused as ELEMENT_REFERENCE_UNRESOLVED, and is left out here.
    contained_children: dict[str, list[tuple[int, str]]] = {entity.UniqueName: [] for entity in file.Entities}
    for position, association in enumerate(file.Associations):
        parent, child = association.Parent.Entity, association.Child
        if (
            isinstance(child, EntityKey)
            and not association.Reference
            and parent in contained_children
            and child.Entity in contained_children
        ):
            contained_children[parent].append((position, child.Entity))
    return contained_children


def _find_containment_cycles(contained_children: dict[str, list[tuple[int, str]]]) -> Iterator[tuple[int, list[str]]]:
    # Walk depth-first from each entity, visiting each entity once (§8). Reaching an entity on the
    # current path is a cycle; reaching one already walked is a shared entity, such as Identifier under
    # both Organization and Person. Yields the position of the association that closes each cycle, and the
    # entities on it.
    #
    # The path is kept in a dict rather than as recursion, because containment may nest thousands of
    # levels deep. It maps each entity on the path to the children it has left to walk. A dict keeps
    # the order its keys were added in, so its last key is the deepest entity, and checking whether an
    # entity is on the path is one lookup however deep the path is.
    walked_entities: set[str] = set()
    for start_entity in contained_children:
        if start_entity in walked_entities:
            continue
        path = {start_entity: iter(contained_children[start_entity])}
        while path:
            deepest_entity, children_left_to_walk = next(reversed(path.items()))
            next_child = next(children_left_to_walk, None)
            if next_child is None:
                # Step back up: every child of the deepest entity has been walked.
                path.popitem()
                walked_entities.add(deepest_entity)
                continue
            association_position, child_entity = next_child
            if child_entity in path:
                entities_on_path = list(path)
                cycle = entities_on_path[entities_on_path.index(child_entity) :]
                yield association_position, [*cycle, child_entity]
            elif child_entity not in walked_entities:
                # Go down into the child.
                path[child_entity] = iter(contained_children[child_entity])


def _check_for_unassociated_attributes(file: ModelFile) -> Iterator[PortabilityError]:
    # Every attribute must be the child of at least one association, because an attribute with none
    # has no place in the generated schema (§5.3). An association whose parent does not resolve still
    # places its child: it is refused as ELEMENT_REFERENCE_UNRESOLVED instead.
    associated_attribute_names = {
        association.Child.Attribute for association in file.Associations if isinstance(association.Child, AttributeKey)
    }
    for position, attribute in enumerate(file.Attributes):
        if attribute.UniqueName not in associated_attribute_names:
            yield PortabilityError(
                PortabilityErrorCode.UNASSOCIATED_ATTRIBUTE,
                _get_item_path("Attributes", attribute.UniqueName, position),
                "the attribute is the child of no association, so it has no place in the generated schema",
            )


def _get_association_key(association: Association) -> str:
    # An association's key is its parent and Name, as in Course, AccreditedBy.
    return f"{association.Parent.Entity}, {association.Name}"


def _get_association_path(association: Association, position: int) -> str:
    return _get_item_path("Associations", _get_association_key(association), position)


def _get_item_path(list_path: str, key: str, position: int) -> str:
    # An item is named by its key, as in Entities[Student], unless the key holds a bracket, which would
    # make the path unreadable (Entities[a]b]). Such an item is named by its position instead, as
    # parse.py names it.
    if "[" in key or "]" in key:
        return f"{list_path}[{position}]"
    return f"{list_path}[{key}]"
