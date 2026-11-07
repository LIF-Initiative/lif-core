"""Tests for create-by-upload reference handling (Issue #756).

MDR's schema generator inlines an entity reference as an object stored under a "Ref"-infix
property key ("Ref<Child>" / "<relationship>Ref<Child>") rather than an OpenAPI "$ref". The
upload reader used to look only for "$ref", so references in an MDR-exported schema were
silently dropped (and materialized as bogus child entities). These tests cover the key parsing,
the reference/child discrimination, and the reference-association post-pass.
"""

import types
import pytest
from unittest.mock import AsyncMock, MagicMock

# asyncio_mode = auto (see pyproject) runs the async tests; sync helper tests stay sync.

svc = pytest.importorskip("lif.mdr_services.schema_upload_service")


# --- pure helpers ---------------------------------------------------------------------------


def test_parse_reference_key_plain():
    assert svc.parse_reference_key("RefOrganization") == (None, "Organization")


def test_parse_reference_key_with_relationship():
    assert svc.parse_reference_key("issuedByRefOrganization") == ("issuedBy", "Organization")


# cspell:ignore erenced - deliberate fragment in the comment below, illustrating a mis-parse
def test_parse_reference_key_relationship_containing_ref():
    # A relationship name can itself contain "Ref" (isReferencedBy, refersTo). rpartition splits
    # on the LAST "Ref", so the child entity name stays intact; splitting on the first would yield
    # ("is", "erencedByRefOrganization") whose lowercase child fails the PascalCase guard and the
    # reference would be silently dropped (cbeach47 #1007 review).
    assert svc.parse_reference_key("isReferencedByRefOrganization") == ("isReferencedBy", "Organization")
    assert svc.is_inlined_reference("isReferencedByRefOrganization", {"type": "object"}) is True


def test_parse_reference_key_has_relevant_relationship_name_is_lost():
    # KNOWN, generator-side loss (tracked in #1062): the generator encodes has*/relevant*
    # relationships WITHOUT the name (schema_generation_service.py:802 -> "Ref" + child), so
    # e.g. hasManager exports as "RefEmployee". The reader can't recover a name that was never
    # emitted, so it round-trips to relationship=None. Asserted here so the loss is documented,
    # not hidden (the round-trip test only uses issuedBy, which survives).
    assert svc.parse_reference_key("RefEmployee") == (None, "Employee")


@pytest.mark.parametrize(
    "prop_name,prop,expected",
    [
        ("RefOrganization", {"type": "object", "properties": {}}, True),
        ("issuedByRefOrganization", {"type": "object", "properties": {}}, True),
        # embedded child whose own name merely contains "Ref" must NOT be read as a reference
        ("Reference", {"type": "object", "properties": {}}, False),
        # a real $ref property is handled by its own branch, not as an inlined reference
        ("RefOrganization", {"$ref": "#/components/schemas/Organization"}, False),
        # attributes carry ValueSetId
        ("someAttr", {"ValueSetId": 1}, False),
        # no marker at all
        ("hasOrganization", {"type": "object", "properties": {}}, False),
        # PascalCase embedded child with no "Ref" marker must NOT be read as a reference — every
        # LIF entity key is PascalCase, so misreading this dropped all nested entities on re-upload
        # (#1007 regression). The camelCase case above didn't catch it (it fails the PascalCase guard).
        ("Courses", {"type": "object", "properties": {}}, False),
    ],
)
def test_is_inlined_reference(prop_name, prop, expected):
    assert svc.is_inlined_reference(prop_name, prop) is expected


# --- reference post-pass --------------------------------------------------------------------


@pytest.fixture
def patched_lookups(monkeypatch):
    """Resolve entities by UniqueName and report no pre-existing association."""
    entities = {
        "Person": types.SimpleNamespace(Id=1, Name="Person", Array=None),
        "Organization": types.SimpleNamespace(Id=2, Name="Organization", Array="Yes"),
    }

    async def fake_get_unique_entity(session, unique_name, data_model_id, base_data_model_id, data_model_type):
        return entities.get(unique_name)

    monkeypatch.setattr(svc, "get_unique_entity", AsyncMock(side_effect=fake_get_unique_entity))
    monkeypatch.setattr(svc, "get_entity_association_by_parent_child_relationship", AsyncMock(return_value=None))
    return entities


def _added_associations(session):
    return [c.args[0] for c in session.add.call_args_list if isinstance(c.args[0], svc.EntityAssociation)]


async def test_inlined_reference_creates_reference_association(patched_lookups):
    session = MagicMock()
    session.add = MagicMock()
    entity_md = {
        "UniqueName": "Person",
        "DataModelId": 7,
        "properties": {
            "issuedByRefOrganization": {
                "type": "object",
                "UniqueName": "Organization",
                "DataModelId": 7,
                "properties": {"identifier": {"type": "string"}},
            }
        },
    }

    await svc.create_reference_associations_for_children(session, "Person", entity_md, 7, {}, "SourceSchema")

    associations = _added_associations(session)
    assert len(associations) == 1
    assoc = associations[0]
    assert assoc.ParentEntityId == 1
    assert assoc.ChildEntityId == 2
    assert assoc.Relationship == "issuedBy"
    assert assoc.Placement == "Reference"
    # #1386: Name is the key the reference was uploaded under.
    # A reference is single, whatever the referenced entity's Array (#1471).
    assert (assoc.Name, assoc.Array) == ("issuedByRefOrganization", False)


async def test_plain_reference_has_no_relationship(patched_lookups):
    session = MagicMock()
    session.add = MagicMock()
    entity_md = {
        "UniqueName": "Person",
        "properties": {"RefOrganization": {"type": "object", "UniqueName": "Organization", "properties": {}}},
    }

    await svc.create_reference_associations_for_children(session, "Person", entity_md, 7, {}, "SourceSchema")

    associations = _added_associations(session)
    assert len(associations) == 1
    assert associations[0].Relationship is None
    assert associations[0].Name == "RefOrganization"


async def test_embedded_child_does_not_create_reference_association(patched_lookups):
    """A non-reference child (no "Ref" marker) is recursed into, not turned into a reference."""
    session = MagicMock()
    session.add = MagicMock()
    entity_md = {
        "UniqueName": "Person",
        "properties": {"hasOrganization": {"type": "object", "UniqueName": "Organization", "properties": {}}},
    }

    await svc.create_reference_associations_for_children(session, "Person", entity_md, 7, {}, "SourceSchema")

    assert _added_associations(session) == []


# --- child pass -----------------------------------------------------------------------------


@pytest.mark.parametrize(("placement", "expected_array"), [("Reference", False), ("Embedded", True)])
async def test_a_child_uploaded_with_a_placement_takes_that_placement_s_array(monkeypatch, placement, expected_array):
    """A child property carrying EntityAssociationPlacement: a Reference one is single (#1471), an
    Embedded one follows the child's Array."""
    parent = types.SimpleNamespace(Id=1, Name="Person", Array=None)
    child = types.SimpleNamespace(Id=2, Name="Course", Array="Yes")
    create_children = svc.create_entity_and_children_if_needed
    monkeypatch.setattr(svc, "create_entity_if_needed", AsyncMock(return_value=parent))
    monkeypatch.setattr(svc, "create_entity_and_children_if_needed", AsyncMock(return_value=child))
    monkeypatch.setattr(svc, "get_entity_association_by_parent_child_relationship", AsyncMock(return_value=None))
    session = MagicMock()
    entity_md = {"properties": {"Course": {"type": "object", "EntityAssociationPlacement": placement}}}

    await create_children(session, "Person", entity_md, 7, None, "UniconQA", "SourceSchema")

    [assoc] = _added_associations(session)
    assert (assoc.ChildEntityId, assoc.Placement, assoc.Array) == (2, placement, expected_array)
