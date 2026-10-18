"""The key a child appears under in its parent, stored as the association's Name (issue #1386).

V1.7 backfills the same rules in SQL; test_association_name_seed.py checks the two agree on the seed.
"""

import pytest

from lif.mdr_services.association_name import association_array, entity_association_name, recomputed
from lif.mdr_sql_model.core import EntityPlacementType

# (relationship, placement, child name, expected Name)
ENTITY_CASES = [
    # Reference: add_ref's key.
    (None, "Reference", "Organization", "RefOrganization"),
    ("", "Reference", "Organization", "RefOrganization"),  # "" + "Ref" + name
    ("hasIssuer", "Reference", "Organization", "RefOrganization"),
    ("relevantIssuer", "Reference", "Organization", "RefOrganization"),
    ("awardedBy", "Reference", "Organization", "awardedByRefOrganization"),
    # Embedded: embedded_property_key.
    (None, "Embedded", "Address", "Address"),
    ("", "Embedded", "Address", "Address"),  # "" + name: the bare name on both branches
    ("hasAddress", "Embedded", "Address", "Address"),
    ("relevantAddress", "Embedded", "Address", "Address"),
    ("mailing", "Embedded", "Address", "mailingAddress"),
    # No placement is treated as Embedded, as the generator does.
    (None, None, "Address", "Address"),
    ("hasAddress", None, "Address", "Address"),
    ("mailing", None, "Address", "mailingAddress"),
    # Case is kept as stored (spec §5.4): no PascalCase/camelCase fix-up.
    ("basisLegal", "Embedded", "Code", "basisLegalCode"),
    ("HasAddress", "Embedded", "Address", "HasAddressAddress"),
]


@pytest.mark.parametrize("relationship, placement, child_name, expected", ENTITY_CASES)
def test_entity_association_name(relationship, placement, child_name, expected):
    assert entity_association_name(relationship, placement, child_name) == expected


def test_placement_may_be_the_model_enum():
    # The ORM hands create paths an EntityPlacementType, not a str.
    assert entity_association_name("awardedBy", EntityPlacementType.Reference, "Org") == "awardedByRefOrg"
    assert entity_association_name("awardedBy", EntityPlacementType.Embedded, "Org") == "awardedByOrg"


@pytest.mark.parametrize(
    "child_array, expected", [("Yes", True), ("No", False), (None, False), ("yes", False), ("", False)]
)
def test_association_array_is_true_only_for_yes(child_array, expected):
    assert association_array(child_array) is expected


@pytest.mark.parametrize(
    ("stored", "before", "after", "expected"),
    [
        ("mailingAddress", "mailingAddress", "homeAddress", "homeAddress"),  # still the rule's: follows the edit
        (None, "mailingAddress", "homeAddress", "homeAddress"),  # not computed yet: computed now
        ("AccreditedBy", "mailingAddress", "homeAddress", "AccreditedBy"),  # set some other way: kept
        (True, True, False, False),  # Array follows the same rule
        (False, True, False, False),
        (True, False, False, True),  # an Array the rule wouldn't give stays, even when the edit changes nothing
    ],
)
def test_recomputed_follows_the_rule_only_while_the_value_is_the_rules(stored, before, after, expected):
    assert recomputed(stored, before, after) == expected
