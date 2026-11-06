"""The overlay conversion's pure parts (#1388): reading the render set from a schema, rewriting a
"before" schema through the Id map, and re-pointing mapping paths.

The rewrite is the conversion's pass criterion, so these pin what it may change (Ids, DataModelId,
ExtendedBy, Extension) and that it changes nothing else.
"""

import pytest

from lif.mdr_services.overlay_converter import IdMap, _map_path, render_set, rewrite_base_schema, rewrite_overlay_schema


def _schema():
    """A FULL schema: Person (17's copy of model 1's 4) holds own entity 342 and an attribute from model 1
    with a value set, plus a reference whose node is a narrowed copy of a rendered entity."""
    return {
        "openapi": "3.0.0",
        "components": {
            "schemas": {
                "Person": {
                    "Id": 4,
                    "DataModelId": 1,
                    "Extension": False,
                    "ExtensionNotes": None,
                    "required": ["name"],
                    "properties": {
                        "name": {
                            "Id": 54,
                            "DataModelId": 1,
                            "Extension": False,
                            "ExtensionNotes": None,
                            "ValueSetId": 287,
                            "EntityId": 4,
                            "EntityAttributeAssociationId": 900,
                            "AssociationExtendedByDataModelId": None,
                            "ValueSet": {
                                "Id": 287,
                                "DataModelId": 1,
                                "Values": [{"Id": 5000, "ValueSetId": 287, "DataModelId": 1, "Value": "a"}],
                            },
                            "enum": ["a"],
                        },
                        "OrgThing": {
                            "Id": 342,
                            "DataModelId": 17,
                            "Extension": True,
                            "ExtensionNotes": "added by StateU",
                            "EntityAssociationId": 158,
                            "EntityAssociationParentEntityId": 4,
                            "EntityAssociationExtendedByDataModelId": 17,
                            "EntityAssociationExtension": True,
                            "EntityAssociationExtensionNotes": "x",
                            "properties": {
                                "flag": {
                                    "Id": 1833,
                                    "DataModelId": 17,
                                    "Extension": True,
                                    "ExtensionNotes": None,
                                    "EntityId": 342,
                                    "EntityAttributeAssociationId": 1795,
                                    "AssociationExtendedByDataModelId": 17,
                                }
                            },
                        },
                    },
                }
            }
        },
    }


def _ids():
    return IdMap(
        entities={4: 2004, 342: 342},
        attributes={54: 3054, 1833: 1833},
        entity_associations={158: 158},
        attribute_associations={900: 4900, 1795: 1795},
        value_sets={287: 6287},
        values={5000: 7000},
    )


def test_render_set_names_every_shown_row():
    rendered = render_set(_schema())

    assert rendered.entities == {4, 342}
    assert rendered.attributes == {54, 1833}
    assert rendered.entity_associations == {158}
    assert rendered.attribute_associations == {900, 1795}


def test_rewrite_maps_every_id_by_its_own_kind_and_makes_everything_the_models():
    after = rewrite_overlay_schema(_schema(), 17, _ids())["components"]["schemas"]["Person"]
    name = after["properties"]["name"]
    own = after["properties"]["OrgThing"]

    assert (after["Id"], after["DataModelId"]) == (2004, 17)
    assert (name["Id"], name["DataModelId"], name["EntityId"], name["EntityAttributeAssociationId"]) == (
        3054,
        17,
        2004,
        4900,
    )
    assert name["ValueSetId"] == 6287
    assert (name["ValueSet"]["Id"], name["ValueSet"]["DataModelId"]) == (6287, 17)
    assert name["ValueSet"]["Values"] == [{"Id": 7000, "ValueSetId": 6287, "DataModelId": 17, "Value": "a"}]
    assert (own["Id"], own["EntityAssociationParentEntityId"]) == (342, 2004)
    # Entity Ids and attribute Ids overlap as numbers; each goes through its own map (D1, per key).
    assert own["properties"]["flag"]["EntityId"] == 342


def test_rewrite_clears_extended_by_and_extension():
    after = rewrite_overlay_schema(_schema(), 17, _ids())["components"]["schemas"]["Person"]
    own = after["properties"]["OrgThing"]

    assert (own["Extension"], own["ExtensionNotes"]) == (False, None)
    assert own["EntityAssociationExtendedByDataModelId"] is None
    assert (own["EntityAssociationExtension"], own["EntityAssociationExtensionNotes"]) == (False, None)
    assert own["properties"]["flag"]["AssociationExtendedByDataModelId"] is None
    assert own["properties"]["flag"]["Extension"] is False


def test_rewrite_changes_nothing_else_and_leaves_its_input_alone():
    before = _schema()

    after = rewrite_overlay_schema(before, 17, _ids())

    assert before == _schema()
    assert after["components"]["schemas"]["Person"]["required"] == ["name"]
    assert after["components"]["schemas"]["Person"]["properties"]["name"]["enum"] == ["a"]
    assert after["openapi"] == "3.0.0"


def test_rewrite_fails_on_a_shown_row_the_map_lacks():
    ids = _ids()
    del ids.attributes[1833]

    with pytest.raises(KeyError):
        rewrite_overlay_schema(_schema(), 17, ids)


def test_a_schema_without_metadata_is_unchanged():
    """attr0-entity0 carries no Ids, so it must come out byte-identical (D1)."""
    plain = {"components": {"schemas": {"Person": {"type": "array", "properties": {"name": {"type": "string"}}}}}}

    assert rewrite_overlay_schema(plain, 17, IdMap()) == plain


def test_an_error_baseline_is_returned_as_it_is():
    error = {"x-http-error": {"status_code": 404, "detail": "x"}}

    assert rewrite_overlay_schema(error, 17, IdMap()) == error


def test_the_base_rewrite_moves_only_step_0s_attributes_to_the_base():
    schema = {
        "components": {
            "schemas": {
                "Person": {
                    "Id": 4,
                    "DataModelId": 1,
                    "properties": {"email": {"Id": 1288, "DataModelId": 17}, "name": {"Id": 54, "DataModelId": 1}},
                }
            }
        }
    }

    properties = rewrite_base_schema(schema, {1288: 1})["components"]["schemas"]["Person"]["properties"]

    assert properties == {"email": {"Id": 1288, "DataModelId": 1}, "name": {"Id": 54, "DataModelId": 1}}


@pytest.mark.parametrize(
    "path, expected",
    [
        ("4,342,-1833", "2004,342,-1833"),
        ("4, 342 ,-54", "2004,342,-3054"),
        # An entity Id and an attribute Id can be the same number; the sign says which map applies.
        ("-4", None),
        ("4,999,-54", None),
        ("LIF.Person.name", None),
    ],
)
def test_map_path(path, expected):
    assert _map_path(path, IdMap(entities={4: 2004, 342: 342}, attributes={54: 3054, 1833: 1833})) == expected
