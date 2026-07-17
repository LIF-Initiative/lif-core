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
    ],
)
def test_is_inlined_reference(prop_name, prop, expected):
    assert svc.is_inlined_reference(prop_name, prop) is expected


# --- reference post-pass --------------------------------------------------------------------


@pytest.fixture
def patched_lookups(monkeypatch):
    """Resolve entities by UniqueName and report no pre-existing association."""
    entities = {
        "Person": types.SimpleNamespace(Id=1, Name="Person"),
        "Organization": types.SimpleNamespace(Id=2, Name="Organization"),
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
