"""Postgres-backed tests of the crosswalk converter (issue #1390).

The file rule is tested in test/components/lif/mdr_portability; these cover what needs installed
models: values resolved against live rows, round trips between installs whose row IDs differ, what
counts as a live value mapping, and refused imports writing nothing.

Model names carry the test name, since the fixture database is shared across the session.
"""

import json

import pytest
from sqlalchemy.orm import aliased
from sqlmodel import func, select

from lif.mdr_portability import PortabilityErrorCode, PortabilityErrorGroup, dump_canonical, parse_crosswalk_file
from lif.mdr_services.crosswalk_converter import export_crosswalk, import_crosswalk
from lif.mdr_sql_model.core import (
    DataModel,
    DataModelType,
    TransformationGroup,
    ValueSet,
    ValueSetValue,
    ValueSetValueMapping,
)

Code = PortabilityErrorCode

# U has no entry in ENTRIES; the liveness test maps it directly.
VALUES = {"Source": ["F", "M", "U", "X"], "Target": ["Female", "Male", "Unknown"]}


async def _install(session, tag, reverse=False):
    """A source and a target model, each with one value set. reverse builds the rows in the opposite
    order, so a second install gets different row IDs. Returns {side: (model, value set, {name: value})}."""
    installed = {}
    for side in ("Target", "Source") if reverse else ("Source", "Target"):
        model = DataModel(
            Name=f"CW{side}_{tag}",
            Type=DataModelType.SourceSchema,
            DataModelVersion="1.0",
            ContributorOrganization="UniconQA",
            Deleted=False,
        )
        session.add(model)
        await session.flush()
        value_set = ValueSet(Name=f"{side}Sex", DataModelId=model.Id, Deleted=False)
        session.add(value_set)
        await session.flush()
        values = {}
        for name in reversed(VALUES[side]) if reverse else VALUES[side]:
            value = ValueSetValue(
                ValueSetId=value_set.Id, DataModelId=model.Id, Value=name, ValueName=name, Deleted=False
            )
            session.add(value)
            await session.flush()
            values[name] = value
        installed[side] = (model, value_set, values)
    await session.commit()
    return installed


def _key(side, tag):
    return {
        "Model": {"Name": f"CW{side}_{tag}", "Version": "1.0", "ContributorOrganization": "UniconQA"},
        "ValueSet": f"{side}Sex",
    }


def _file(tag, entries, **details) -> bytes:
    data = {
        "Format": {"Type": "lif-mdr-crosswalk", "Version": 1},
        "Details": {"Source": _key("Source", tag), "Target": _key("Target", tag)} | details,
        "Entries": entries,
    }
    return dump_canonical(parse_crosswalk_file(json.dumps(data).encode()))


ENTRIES = [
    {"Source": "F", "Target": "Female", "Notes": "as coded", "ActivationDate": "2026-02-11T10:04:02.843Z"},
    {"Source": "M", "Target": "Male", "Contributor": "QA", "ContributorOrganization": "UniconQA"},
    {
        "Source": "X",
        "Target": "Unknown",
        "Description": "not stated",
        "UseConsiderations": "rare",
        "DeprecationDate": "2027-01-01T00:00:00Z",
    },
]


def _ids(installed):
    return installed["Source"][1].Id, installed["Target"][1].Id


def _codes(error: PortabilityErrorGroup) -> list:
    return sorted(e.code for e in error.exceptions)


def _refusals(error: PortabilityErrorGroup) -> list:
    return [(e.code, e.element) for e in error.exceptions]


def _add_mapping(session, installed, source: str, target: str) -> ValueSetValueMapping:
    mapping = ValueSetValueMapping(
        SourceValueId=installed["Source"][2][source].Id, TargetValueId=installed["Target"][2][target].Id, Deleted=False
    )
    session.add(mapping)
    return mapping


async def _mapping_count(session) -> int:
    return (await session.execute(select(func.count()).select_from(ValueSetValueMapping))).scalar_one()


async def test_a_crosswalk_round_trips_between_installs_byte_for_byte(test_db_session):
    session, tag = test_db_session, "roundtrip"
    file_a = _file(tag, ENTRIES)

    installed_1 = await _install(session, tag)
    assert await import_crosswalk(session, parse_crosswalk_file(file_a)) == 3
    await session.commit()
    file_b = dump_canonical(await export_crosswalk(session, *_ids(installed_1)))
    assert file_b == file_a

    # A second install: the same models by identity, built in reverse so every row ID differs.
    for model, _, _ in installed_1.values():
        model.Deleted = True
    await session.commit()
    installed_2 = await _install(session, tag, reverse=True)
    await import_crosswalk(session, parse_crosswalk_file(file_b))
    await session.commit()
    file_c = dump_canonical(await export_crosswalk(session, *_ids(installed_2)))
    assert file_c == file_a

    rows = (
        await session.execute(
            select(ValueSetValueMapping).where(ValueSetValueMapping.SourceValueSetId == installed_2["Source"][1].Id)
        )
    ).scalars()
    female = installed_2["Target"][2]["Female"].Id
    stored = {row.TargetValueId: row for row in rows}
    assert len(stored) == 3
    assert stored[female].SourceValueId == installed_2["Source"][2]["F"].Id
    assert stored[female].TargetValueSetId == installed_2["Target"][1].Id
    assert all(row.TransformationGroupId is None for row in stored.values())


@pytest.mark.parametrize(
    "tag, entries, details, refusals",
    [
        (
            "dup",
            ENTRIES + [{"Source": "F", "Target": "Unknown"}],
            {},
            [(Code.CROSSWALK_SOURCE_DUPLICATE, "Entries[F]")],
        ),
        (
            "missing_value",
            [{"Source": "Z", "Target": "Female"}, {"Source": "F", "Target": "Woman"}],
            {},
            [
                (Code.ELEMENT_REFERENCE_UNRESOLVED, "Entries[F].Target"),
                (Code.ELEMENT_REFERENCE_UNRESOLVED, "Entries[Z].Source"),
            ],
        ),
        (
            "missing_set",
            ENTRIES,
            {"Target": _key("Target", "missing_set") | {"ValueSet": "Gender"}},
            [(Code.ELEMENT_REFERENCE_UNRESOLVED, "Details.Target.ValueSet")],
        ),
        (
            "missing_model",
            ENTRIES,
            {"Source": _key("Source", "elsewhere")},
            [(Code.MODEL_MISSING, "Details.Source.Model")],
        ),
    ],
)
async def test_a_refused_import_writes_nothing(test_db_session, tag, entries, details, refusals):
    session = test_db_session
    await _install(session, tag)
    before = await _mapping_count(session)
    with pytest.raises(PortabilityErrorGroup) as exc_info:
        await import_crosswalk(session, parse_crosswalk_file(_file(tag, entries, **details)))
    assert sorted((e.code, e.element) for e in exc_info.value.exceptions) == refusals
    # Counted in the same session, before the rollback, so a flushed partial write would show.
    assert await _mapping_count(session) == before
    await session.rollback()


async def test_import_refuses_a_pair_that_is_already_mapped(test_db_session):
    session, tag = test_db_session, "exists"
    await _install(session, tag)
    await import_crosswalk(session, parse_crosswalk_file(_file(tag, ENTRIES[:1])))
    await session.commit()
    before = await _mapping_count(session)
    with pytest.raises(PortabilityErrorGroup) as exc_info:
        await import_crosswalk(session, parse_crosswalk_file(_file(tag, ENTRIES[1:])))
    assert _codes(exc_info.value) == [Code.CROSSWALK_EXISTS]
    # Counted in the same session, before the rollback, so a flushed partial write would show.
    assert await _mapping_count(session) == before
    await session.rollback()


@pytest.mark.parametrize(
    "tag, delete, element",
    [
        ("dead_value", lambda installed: installed["Target"][2]["Female"], "Entries[F].Target"),
        ("dead_set", lambda installed: installed["Target"][1], "Details.Target.ValueSet"),
    ],
)
async def test_import_resolves_only_live_value_sets_and_values(test_db_session, tag, delete, element):
    session = test_db_session
    installed = await _install(session, tag)
    delete(installed).Deleted = True
    await session.commit()
    before = await _mapping_count(session)
    with pytest.raises(PortabilityErrorGroup) as exc_info:
        await import_crosswalk(session, parse_crosswalk_file(_file(tag, ENTRIES)))
    assert [(e.code, e.element) for e in exc_info.value.exceptions] == [(Code.ELEMENT_REFERENCE_UNRESOLVED, element)]
    assert await _mapping_count(session) == before
    await session.rollback()


async def test_export_leaves_out_mappings_that_are_not_live(test_db_session):
    session, tag = test_db_session, "live"
    installed = await _install(session, tag)
    await import_crosswalk(session, parse_crosswalk_file(_file(tag, ENTRIES)))
    await session.commit()
    rows = {
        row.SourceValueId: row
        for row in (
            await session.execute(
                select(ValueSetValueMapping).where(ValueSetValueMapping.SourceValueSetId == installed["Source"][1].Id)
            )
        ).scalars()
    }
    sources = installed["Source"][2]

    # F's target value is deleted; U's source value is deleted; M is in a deleted group; X stays
    # live, in a live group.
    installed["Target"][2]["Female"].Deleted = True
    _add_mapping(session, installed, "U", "Unknown")
    sources["U"].Deleted = True
    deleted_group = TransformationGroup(
        SourceDataModelId=installed["Source"][0].Id,
        TargetDataModelId=installed["Target"][0].Id,
        Name=f"deleted_{tag}",
        GroupVersion="1.0",
        Deleted=True,
    )
    live_group = TransformationGroup(
        SourceDataModelId=installed["Source"][0].Id,
        TargetDataModelId=installed["Target"][0].Id,
        Name=f"live_{tag}",
        GroupVersion="1.1",
        Deleted=False,
    )
    session.add_all([deleted_group, live_group])
    await session.flush()
    rows[sources["M"].Id].TransformationGroupId = deleted_group.Id
    rows[sources["X"].Id].TransformationGroupId = live_group.Id
    await session.commit()

    file = await export_crosswalk(session, *_ids(installed))
    assert [(entry.Source, entry.Target) for entry in file.Entries] == [("X", "Unknown")]


async def test_export_refuses_stored_values_the_format_does_not_allow(test_db_session):
    session = test_db_session
    installed = await _install(session, "export_blanks")
    _add_mapping(session, installed, "F", "Female")
    _add_mapping(session, installed, "X", "Unknown")
    installed["Target"][2]["Unknown"].ValueName = ""
    installed["Source"][1].Name = "  "
    await session.commit()

    with pytest.raises(PortabilityErrorGroup) as exc_info:
        await export_crosswalk(session, *_ids(installed))
    # Named by key, never by row Id (§10).
    assert sorted(_refusals(exc_info.value)) == [
        (Code.FIELD_INVALID, "Details.Source.ValueSet"),
        (Code.FIELD_INVALID, "Entries[X].Target"),
    ]


async def test_export_refuses_a_source_mapped_twice(test_db_session):
    session = test_db_session
    installed = await _install(session, "export_dup")
    _add_mapping(session, installed, "F", "Female")
    _add_mapping(session, installed, "F", "Male")
    await session.commit()

    with pytest.raises(PortabilityErrorGroup) as exc_info:
        await export_crosswalk(session, *_ids(installed))
    assert _refusals(exc_info.value) == [(Code.CROSSWALK_SOURCE_DUPLICATE, "Entries[F]")]


@pytest.mark.parametrize(
    "tag, field, value",
    [
        # Seed model 26 has no ContributorOrganization.
        ("identity_null", "ContributorOrganization", None),
        ("identity_blank", "DataModelVersion", " "),
    ],
)
async def test_export_refuses_a_model_with_an_incomplete_identity(test_db_session, tag, field, value):
    session = test_db_session
    installed = await _install(session, tag)
    _add_mapping(session, installed, "F", "Female")
    setattr(installed["Target"][0], field, value)
    await session.commit()

    with pytest.raises(PortabilityErrorGroup) as exc_info:
        await export_crosswalk(session, *_ids(installed))
    file_field = "Version" if field == "DataModelVersion" else field
    assert _refusals(exc_info.value) == [(Code.MODEL_IDENTITY_INCOMPLETE, f"Details.Target.Model.{file_field}")]


async def test_export_refuses_a_value_set_whose_model_is_deleted(test_db_session):
    session = test_db_session
    installed = await _install(session, "export_model")
    _add_mapping(session, installed, "F", "Female")
    installed["Source"][0].Deleted = True
    await session.commit()

    with pytest.raises(PortabilityErrorGroup) as exc_info:
        await export_crosswalk(session, *_ids(installed))
    assert _refusals(exc_info.value) == [(Code.MODEL_MISSING, "Details.Source.Model")]


async def test_export_refuses_a_value_set_that_is_missing_or_deleted(test_db_session):
    session = test_db_session
    installed = await _install(session, "export_set")
    installed["Target"][1].Deleted = True
    await session.commit()
    source_id, target_id = _ids(installed)

    for ids in ((source_id, target_id), (source_id, -1)):
        with pytest.raises(PortabilityErrorGroup) as exc_info:
            await export_crosswalk(session, *ids)
        assert _refusals(exc_info.value) == [(Code.ELEMENT_REFERENCE_UNRESOLVED, "Details.Target.ValueSet")]


async def test_a_pair_with_no_live_mappings_exports_no_entries_and_imports_nothing(test_db_session):
    session = test_db_session
    installed = await _install(session, "empty")
    file = await export_crosswalk(session, *_ids(installed))
    assert file.Entries == []

    before = await _mapping_count(session)
    assert await import_crosswalk(session, parse_crosswalk_file(dump_canonical(file))) == 0
    assert await _mapping_count(session) == before


async def test_every_seed_crosswalk_exports_and_round_trips(seed_db_session):
    """The seed's live value mappings: 7 pairs. Every crosswalk is exported, its rows are soft-deleted
    and the file is imported back, and exporting again gives the same bytes. Nothing is committed."""
    session = seed_db_session
    source_value, target_value = aliased(ValueSetValue), aliased(ValueSetValue)
    source_set, target_set = aliased(ValueSet), aliased(ValueSet)
    pairs = (
        await session.execute(
            select(source_value.ValueSetId, target_value.ValueSetId)
            .select_from(ValueSetValueMapping)
            .join(source_value, source_value.Id == ValueSetValueMapping.SourceValueId)
            .join(target_value, target_value.Id == ValueSetValueMapping.TargetValueId)
            .join(source_set, source_set.Id == source_value.ValueSetId)
            .join(target_set, target_set.Id == target_value.ValueSetId)
            .where(
                ValueSetValueMapping.Deleted.is_not(True),
                source_value.Deleted.is_not(True),
                target_value.Deleted.is_not(True),
                source_set.Deleted.is_not(True),
                target_set.Deleted.is_not(True),
            )
            .distinct()
            .order_by(source_value.ValueSetId, target_value.ValueSetId)
        )
    ).all()
    assert len(pairs) == 7

    try:
        files = {pair: dump_canonical(await export_crosswalk(session, *pair)) for pair in pairs}
        # 716 live rows with live ends, less 2347, whose group 17 is deleted.
        assert sum(len(json.loads(file)["Entries"]) for file in files.values()) == 715

        for (source_id, target_id), file_a in files.items():
            values = aliased(ValueSetValue)
            live = (
                await session.execute(
                    select(ValueSetValueMapping)
                    .join(source_value, source_value.Id == ValueSetValueMapping.SourceValueId)
                    .join(values, values.Id == ValueSetValueMapping.TargetValueId)
                    .where(source_value.ValueSetId == source_id, values.ValueSetId == target_id)
                    .where(ValueSetValueMapping.Deleted.is_not(True))
                )
            ).scalars()
            for row in live:
                row.Deleted = True
            await session.flush()

            await import_crosswalk(session, parse_crosswalk_file(file_a))
            assert dump_canonical(await export_crosswalk(session, source_id, target_id)) == file_a
    finally:
        await session.rollback()
