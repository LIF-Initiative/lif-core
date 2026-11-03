from pathlib import Path

import pytest

from lif.mdr_portability import ModelFile, PortabilityErrorCode, PortabilityErrorGroup, check_model_file
from lif.mdr_portability.v1.models import Association, AttributeKey, EntityKey, ValueSetKey

Code = PortabilityErrorCode
FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str = "test_reference_target_model_file.json") -> ModelFile:
    return ModelFile.model_validate_json((FIXTURES / name).read_text())


def _collect_refusals(file: ModelFile) -> list[tuple[PortabilityErrorCode, str]]:
    with pytest.raises(PortabilityErrorGroup) as exc_info:
        check_model_file(file)
    return [(error.code, error.element) for error in exc_info.value.exceptions]


@pytest.mark.parametrize("fixture", ["test_reference_source_model_file.json", "test_reference_target_model_file.json"])
def test_reference_models_pass(fixture):
    check_model_file(_load(fixture))


@pytest.mark.parametrize(
    "list_name, key_field", [("ValueSets", "Name"), ("Entities", "UniqueName"), ("Attributes", "UniqueName")]
)
def test_two_items_sharing_a_key_are_refused_once(list_name, key_field):
    file = _load()
    items = getattr(file, list_name)
    items.append(items[0].model_copy())
    items.append(items[0].model_copy())
    with pytest.raises(PortabilityErrorGroup) as exc_info:
        check_model_file(file)
    [error] = exc_info.value.exceptions
    key = getattr(items[0], key_field)
    assert (error.code, error.element) == (Code.DUPLICATE_KEY, f"{list_name}[{key}]")
    assert error.reason.startswith("3 ")


def test_an_entity_and_an_attribute_may_share_a_unique_name():
    # The target model already has both an entity and an attribute named Competency.Classifier.
    file = _load()
    assert "Competency.Classifier" in {entity.UniqueName for entity in file.Entities}
    assert "Competency.Classifier" in {attribute.UniqueName for attribute in file.Attributes}
    check_model_file(file)


def test_two_values_sharing_a_value_name_in_one_value_set_are_refused():
    file = _load()
    values = file.ValueSets[0].Values
    values.append(values[0].model_copy(update={"Value": "other"}))
    assert _collect_refusals(file) == [
        (Code.DUPLICATE_KEY, f"ValueSets[{file.ValueSets[0].Name}].Values[{values[0].ValueName}]")
    ]


def test_values_in_different_value_sets_may_share_a_value_name():
    file = _load()
    file.ValueSets[1].Values.append(file.ValueSets[0].Values[0].model_copy())
    check_model_file(file)


def test_keys_are_compared_exactly():
    # As the database's unique indexes compare them (§4.3): case and whitespace make a different key.
    file = _load()
    entity = file.Entities[0]
    for unique_name in (entity.UniqueName.lower(), f"{entity.UniqueName} ", f" {entity.UniqueName}"):
        file.Entities.append(entity.model_copy(update={"UniqueName": unique_name, "Name": unique_name}))
    check_model_file(file)


def test_every_duplicate_is_reported_at_once():
    file = _load()
    file.Entities.append(file.Entities[0].model_copy())
    file.Attributes.append(file.Attributes[0].model_copy())
    assert _collect_refusals(file) == [
        (Code.DUPLICATE_KEY, f"Entities[{file.Entities[0].UniqueName}]"),
        (Code.DUPLICATE_KEY, f"Attributes[{file.Attributes[0].UniqueName}]"),
    ]


def test_an_attribute_value_set_that_names_no_value_set_is_refused():
    file = _load()
    file.ValueSets = [value_set for value_set in file.ValueSets if value_set.Name != "LunchStatus"]
    assert _collect_refusals(file) == [(Code.ELEMENT_REFERENCE_UNRESOLVED, "Attributes[Person.lunchStatus].ValueSet")]


def _find_association(file: ModelFile, parent: str, name: str):
    return next(
        association
        for association in file.Associations
        if association.Parent.Entity == parent and association.Name == name
    )


def test_a_parent_that_names_no_entity_is_refused():
    file = _load()
    _find_association(file, "Course", "AccreditedBy").Parent = EntityKey(Entity="Missing")
    assert _collect_refusals(file) == [
        (Code.ELEMENT_REFERENCE_UNRESOLVED, "Associations[Missing, AccreditedBy].Parent")
    ]


@pytest.mark.parametrize(
    "child",
    [
        EntityKey(Entity="Missing"),
        AttributeKey(Attribute="Missing"),
        # Course is an entity, not an attribute: an element reference resolves only to its own kind (§4.3).
        AttributeKey(Attribute="Course"),
    ],
)
def test_a_child_that_names_no_element_of_its_kind_is_refused(child):
    file = _load()
    _find_association(file, "Competency", "Classifier").Child = child
    assert _collect_refusals(file) == [
        (Code.ELEMENT_REFERENCE_UNRESOLVED, "Associations[Competency, Classifier].Child")
    ]


def test_a_reference_flag_on_an_attribute_child_is_refused():
    file = _load()
    association = _find_association(file, "Competency", "classifier")
    assert isinstance(association.Child, AttributeKey)
    association.Reference = True
    assert _collect_refusals(file) == [(Code.REFERENCE_INVALID, "Associations[Competency, classifier].Reference")]


def test_a_reference_flag_on_an_entity_child_is_allowed():
    file = _load()
    association = _find_association(file, "Competency", "Classifier")
    assert isinstance(association.Child, EntityKey) and not association.Reference
    association.Reference = True
    check_model_file(file)


def test_two_children_under_one_parent_with_the_same_name_are_refused():
    file = _load()
    _find_association(file, "Course", "ApprovedBy").Name = "AccreditedBy"
    assert _collect_refusals(file) == [(Code.ASSOCIATION_NAME_TAKEN, "Associations[Course, AccreditedBy]")]


def test_an_entity_child_and_an_attribute_child_with_the_same_name_are_refused():
    # Under one parent, a Name is taken whatever the kind of child holds it.
    file = _load()
    _find_association(file, "Competency", "classifier").Name = "Classifier"
    assert _collect_refusals(file) == [(Code.ASSOCIATION_NAME_TAKEN, "Associations[Competency, Classifier]")]


def test_association_names_need_only_be_unique_under_their_parent():
    # The target model already has the same child under two names (roles), the same Name under two
    # parents, and two names that differ only by case.
    file = _load()
    roles = [_find_association(file, "Course", name).Child for name in ("AccreditedBy", "ApprovedBy")]
    assert roles == [EntityKey(Entity="Organization")] * 2
    assert _find_association(file, "Organization", "Identifier") and _find_association(file, "Person", "Identifier")
    assert _find_association(file, "Competency", "Classifier") and _find_association(file, "Competency", "classifier")
    check_model_file(file)


def _add_organization_copy(file: ModelFile, unique_name: str) -> None:
    # Another entity with Organization's Name, and no associations.
    organization = next(entity for entity in file.Entities if entity.UniqueName == "Organization")
    file.Entities.append(organization.model_copy(update={"UniqueName": unique_name}))


def test_two_entities_with_no_parent_and_the_same_name_are_refused():
    # Organization's only parents are references, which do not give it a parent (§5.4).
    file = _load()
    assert all(
        association.Reference
        for association in file.Associations
        if association.Child == EntityKey(Entity="Organization")
    )
    _add_organization_copy(file, "Organization.Copy")
    with pytest.raises(PortabilityErrorGroup) as exc_info:
        check_model_file(file)
    [error] = exc_info.value.exceptions
    assert (error.code, error.element) == (Code.TOP_LEVEL_NAME_TAKEN, "Entities[Organization]")
    assert error.reason == "2 entities with no parent have the Name 'Organization': 'Organization', 'Organization.Copy'"


def test_an_entity_with_a_parent_may_share_a_name_with_one_without():
    file = _load()
    _add_organization_copy(file, "Person.Employer")
    _add_containing_association(file, "Person", "Person.Employer", "Employer")
    check_model_file(file)


def _add_containing_association(file: ModelFile, parent: str, child: str, name: str) -> None:
    file.Associations.append(Association(Parent=EntityKey(Entity=parent), Child=EntityKey(Entity=child), Name=name))


def _collect_cycle_errors(file: ModelFile) -> list[tuple[str, str]]:
    with pytest.raises(PortabilityErrorGroup) as exc_info:
        check_model_file(file)
    assert {error.code for error in exc_info.value.exceptions} == {Code.ASSOCIATION_CYCLE}
    return [(error.element, error.reason.split(": ", 1)[1]) for error in exc_info.value.exceptions]


def test_an_entity_that_contains_itself_is_refused():
    file = _load()
    _add_containing_association(file, "Person", "Person", "Self")
    assert _collect_cycle_errors(file) == [("Associations[Person, Self]", "'Person', 'Person'")]


@pytest.mark.parametrize(
    "parent, cycle",
    [
        ("Person.Contact", "'Person', 'Person.Contact', 'Person'"),
        ("Person.Contact.Address", "'Person', 'Person.Contact', 'Person.Contact.Address', 'Person'"),
    ],
)
def test_a_cycle_through_several_entities_is_refused_naming_them_in_order(parent, cycle):
    file = _load()
    _add_containing_association(file, parent, "Person", "Owner")
    assert _collect_cycle_errors(file) == [(f"Associations[{parent}, Owner]", cycle)]


def test_a_cycle_below_the_first_entity_walked_leaves_that_entity_out():
    # The walk starts at Person, but the cycle is between two entities below it.
    file = _load()
    _add_containing_association(file, "Person.Contact.Address", "Person.Contact", "Back")
    assert _collect_cycle_errors(file) == [
        ("Associations[Person.Contact.Address, Back]", "'Person.Contact', 'Person.Contact.Address', 'Person.Contact'")
    ]


def test_a_cycle_on_a_shared_entity_is_reported_once():
    # Identifier is contained by both Organization and Person, but is walked once.
    file = _load()
    _add_containing_association(file, "Identifier", "Identifier", "Self")
    assert _collect_cycle_errors(file) == [("Associations[Identifier, Self]", "'Identifier', 'Identifier'")]


def test_a_cycle_inside_an_entity_reached_only_by_reference_is_refused():
    # Organization's only parents, Course's AccreditedBy and ApprovedBy, are references. A reference
    # is not followed, but every entity is walked, so a cycle inside Organization is still found.
    file = _load()
    assert all(
        association.Reference
        for association in file.Associations
        if association.Child == EntityKey(Entity="Organization")
    )
    _add_containing_association(file, "Organization", "Organization", "Branch")
    assert _collect_cycle_errors(file) == [("Associations[Organization, Branch]", "'Organization', 'Organization'")]


def test_each_cycle_is_reported():
    file = _load()
    _add_containing_association(file, "Person", "Person", "Self")
    _add_containing_association(file, "Course", "Course", "Prerequisite")
    assert [element for element, _ in _collect_cycle_errors(file)] == [
        "Associations[Course, Prerequisite]",
        "Associations[Person, Self]",
    ]


def test_a_cycle_through_a_reference_and_a_shared_entity_are_allowed():
    # The target model already has both: Competency entails Competencies by reference, and Identifier
    # is contained by both Organization and Person.
    file = _load()
    assert _find_association(file, "Competency", "Entails").Reference
    assert _find_association(file, "Organization", "Identifier") and _find_association(file, "Person", "Identifier")
    check_model_file(file)


def test_associations_with_a_missing_entity_are_left_out_of_the_cycle_check():
    file = _load()
    _add_containing_association(file, "Person", "Missing", "Lost")
    _add_containing_association(file, "Missing", "Person", "Found")
    assert _collect_refusals(file) == [
        (Code.ELEMENT_REFERENCE_UNRESOLVED, "Associations[Person, Lost].Child"),
        (Code.ELEMENT_REFERENCE_UNRESOLVED, "Associations[Missing, Found].Parent"),
    ]


def test_containment_thousands_of_levels_deep_is_walked():
    # Deeper than Python's recursion limit, which a recursive walk would hit.
    file = _load()
    chain = [f"Level{depth}" for depth in range(2000)]
    file.Entities.extend(
        file.Entities[0].model_copy(update={"UniqueName": name, "Name": name, "Array": False}) for name in chain
    )
    for parent, child in zip(chain, chain[1:]):
        _add_containing_association(file, parent, child, child)
    check_model_file(file)
    _add_containing_association(file, chain[-1], chain[0], "Back")
    [(element, cycle)] = _collect_cycle_errors(file)
    assert element == f"Associations[{chain[-1]}, Back]"
    assert cycle.count(", ") == len(chain)


def _remove_association(file: ModelFile, parent: str, name: str) -> None:
    file.Associations.remove(_find_association(file, parent, name))


def test_an_attribute_in_no_association_is_refused():
    file = _load()
    _remove_association(file, "Person", "ssn")
    assert _collect_refusals(file) == [(Code.UNASSOCIATED_ATTRIBUTE, "Attributes[Person.ssn]")]


def test_an_entity_association_does_not_count_for_an_attribute_with_the_same_name():
    # The target model has an entity and an attribute both named Competency.Classifier, each the child
    # of its own association under Competency. With the attribute's association removed, the entity's
    # association names the same key, but as an entity, so the attribute is in no association.
    file = _load()
    _remove_association(file, "Competency", "classifier")
    assert isinstance(_find_association(file, "Competency", "Classifier").Child, EntityKey)
    assert _collect_refusals(file) == [(Code.UNASSOCIATED_ATTRIBUTE, "Attributes[Competency.Classifier]")]


def test_an_attribute_whose_association_has_a_missing_parent_is_refused_only_as_unresolved():
    file = _load()
    _find_association(file, "Person", "ssn").Parent = EntityKey(Entity="Missing")
    assert _collect_refusals(file) == [(Code.ELEMENT_REFERENCE_UNRESOLVED, "Associations[Missing, ssn].Parent")]


# A key holding a bracket would make a path unreadable (Entities[a]b]), so the item is named by its
# position instead, as parse_model_file names it.


def test_a_duplicate_key_holding_a_bracket_is_named_by_its_first_position():
    file = _load()
    first_position = len(file.Entities)
    file.Entities.extend(file.Entities[0].model_copy(update={"UniqueName": "a]b", "Name": "a]b"}) for _ in range(2))
    assert _collect_refusals(file) == [(Code.DUPLICATE_KEY, f"Entities[{first_position}]")]


def test_a_value_set_whose_name_holds_a_bracket_is_named_by_its_position_in_a_value_path():
    file = _load()
    value_set = file.ValueSets[0]
    value_set.Name = "Address[Type]"
    for attribute in file.Attributes:
        if attribute.ValueSet and attribute.ValueSet.ValueSet == "AddressType":
            attribute.ValueSet.ValueSet = value_set.Name
    value_set.Values.append(value_set.Values[0].model_copy())
    assert _collect_refusals(file) == [(Code.DUPLICATE_KEY, f"ValueSets[0].Values[{value_set.Values[0].ValueName}]")]


def _find_attribute_position(file: ModelFile, unique_name: str) -> int:
    return next(position for position, attribute in enumerate(file.Attributes) if attribute.UniqueName == unique_name)


def test_an_unresolved_value_set_on_an_attribute_whose_key_holds_a_bracket_is_named_by_its_position():
    file = _load()
    position = _find_attribute_position(file, "Person.lunchStatus")
    file.Attributes[position].UniqueName = "lunch[Status]"
    _find_association(file, "Person", "lunchStatus").Child = AttributeKey(Attribute="lunch[Status]")
    file.Attributes[position].ValueSet = ValueSetKey(ValueSet="Missing")
    assert _collect_refusals(file) == [(Code.ELEMENT_REFERENCE_UNRESOLVED, f"Attributes[{position}].ValueSet")]


def test_an_unassociated_attribute_whose_key_holds_a_bracket_is_named_by_its_position():
    file = _load()
    position = _find_attribute_position(file, "Person.ssn")
    file.Attributes[position].UniqueName = "ssn[1]"
    _remove_association(file, "Person", "ssn")
    assert _collect_refusals(file) == [(Code.UNASSOCIATED_ATTRIBUTE, f"Attributes[{position}]")]


def _find_association_position(file: ModelFile, parent: str, name: str) -> int:
    return file.Associations.index(_find_association(file, parent, name))


def test_associations_whose_name_holds_a_bracket_are_named_by_their_position():
    file = _load()
    first_position = _find_association_position(file, "Course", "AccreditedBy")
    second_position = _find_association_position(file, "Course", "ApprovedBy")
    attribute_position = _find_association_position(file, "Competency", "classifier")
    for position in (first_position, second_position):
        file.Associations[position].Name = "By[Organization]"
    file.Associations[attribute_position].Name = "classifier[]"
    file.Associations[attribute_position].Reference = True
    _add_containing_association(file, "Person", "Person", "Self[]")
    cycle_position = len(file.Associations) - 1
    assert _collect_refusals(file) == [
        (Code.REFERENCE_INVALID, f"Associations[{attribute_position}].Reference"),
        (Code.ASSOCIATION_NAME_TAKEN, f"Associations[{first_position}]"),
        (Code.ASSOCIATION_CYCLE, f"Associations[{cycle_position}]"),
    ]


def test_array_on_an_entity_with_no_parent_is_allowed():
    # Competency's only parent association is a reference, so it has no parent, and the target model
    # makes its top-level schema a list.
    file = _load()
    competency = next(entity for entity in file.Entities if entity.UniqueName == "Competency")
    assert competency.Array
    check_model_file(file)


def test_array_on_an_entity_with_a_parent_is_refused():
    # Person.Contact's list setting is on its association with Person.
    file = _load()
    contact = next(entity for entity in file.Entities if entity.UniqueName == "Person.Contact")
    contact.Array = True
    assert _collect_refusals(file) == [(Code.FIELD_INVALID, "Entities[Person.Contact].Array")]


def test_array_on_an_entity_reached_only_by_reference_is_allowed():
    # A reference does not give its child a parent, so Organization has none (§5.4).
    file = _load()
    organization = next(entity for entity in file.Entities if entity.UniqueName == "Organization")
    organization.Array = True
    check_model_file(file)
