"""The portable format's round trip, run on the shipped seed (#1063; Portability Spec §3, guarantee 5).

Every model, mapping group and crosswalk in backup.sql that the converter exports is file A. Importing A
into an empty install and exporting it gives B; importing B into a second empty install gives C, and
A == B == C byte for byte. The installs are empty tenant schemas from clone_lif_schema, and the second
one's sequences start at 1000, so all three hold the same content under different row Ids.

Content is discovered, not listed: a model, group or crosswalk joins the round trip as soon as it
exports, and a group or crosswalk once both of its models do. On today's seed only models 4 (CEDS),
10 (CTDL) and 13 (ANS) export (test/scripts/test_measure_export_blockers.py). Every exportable group
and crosswalk needs model 1 (LIF), which is NOT_MIGRATED, so none of them round-trip yet.
"""

from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

import psycopg2
import pytest
from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import aliased

from lif.mdr_portability import dump_canonical, parse_crosswalk_file, parse_mapping_group_file, parse_model_file
from lif.mdr_portability.errors import PortabilityErrorGroup
from lif.mdr_services.portability_converter import (
    export_crosswalk,
    export_mapping_group,
    export_model,
    import_crosswalk,
    import_mapping_group,
    import_model,
)
from lif.mdr_sql_model.core import DataModel, TransformationGroup, ValueSet, ValueSetValue, ValueSetValueMapping

INSTALLS = ("tenant_rt_one", "tenant_rt_two")
# The seed models that export today. Raise this as #1388/#1393 migrate more of the seed.
EXPORTING_MODELS = {4, 10, 13}


@dataclass
class PortableFile:
    kind: str  # "model", "group" or "crosswalk", in the order they must be imported
    label: str
    content: bytes


@pytest.fixture(scope="module")
def database_url(seed_postgres):
    """The seed database's URL, with the two empty installs created in it."""
    parsed = urlparse(seed_postgres.url())
    conn = psycopg2.connect(
        host=parsed.hostname,
        port=parsed.port,
        user=parsed.username,
        password=parsed.password or "",
        dbname=parsed.path.lstrip("/"),
    )
    conn.autocommit = True
    with conn.cursor() as cursor:
        for schema in INSTALLS:
            cursor.execute("SELECT public.clone_lif_schema(%s, false)", (schema,))
        cursor.execute(
            "SELECT setval(format('%%I.%%I', schemaname, sequencename), 1000) FROM pg_sequences WHERE schemaname = %s",
            (INSTALLS[1],),
        )
    conn.close()
    return (
        f"postgresql+asyncpg://{parsed.username}:{parsed.password or ''}@{parsed.hostname}:{parsed.port}{parsed.path}"
    )


async def _open(database_url: str, schema: Optional[str] = None):
    # On the connection, so the search_path outlives each commit. public stays on it for the enum types.
    connect_args = {"server_settings": {"search_path": f"{schema},public"}} if schema else {}
    engine = create_async_engine(database_url, connect_args=connect_args)
    return engine, AsyncSession(engine, expire_on_commit=False)


async def _try(export, *args) -> Optional[bytes]:
    """The export's canonical bytes, or None when the converter refuses it."""
    try:
        return dump_canonical(await export(*args))
    except PortabilityErrorGroup:
        return None


async def _discover(session: AsyncSession) -> tuple[list[PortableFile], set[int]]:
    """Every seed file that exports, models first, and the Ids of the models among them."""
    files = []
    model_ids = set()
    for model in (await session.execute(select(DataModel).where(DataModel.Deleted.is_not(True)))).scalars():
        content = await _try(export_model, session, model.Id)
        if content is not None:
            files.append(PortableFile("model", f"model {model.Id} {model.Name}", content))
            model_ids.add(model.Id)

    groups = select(TransformationGroup.Id).where(
        TransformationGroup.Deleted.is_not(True),
        TransformationGroup.SourceDataModelId.in_(model_ids),
        TransformationGroup.TargetDataModelId.in_(model_ids),
    )
    for group_id in (await session.execute(groups)).scalars():
        content = await _try(export_mapping_group, session, group_id)
        if content is not None:
            files.append(PortableFile("group", f"group {group_id}", content))

    # A crosswalk's pair is read from its values, as export_crosswalk reads it.
    source_value, target_value = aliased(ValueSetValue), aliased(ValueSetValue)
    source_set, target_set = aliased(ValueSet), aliased(ValueSet)
    pairs = (
        select(distinct(source_value.ValueSetId), target_value.ValueSetId)
        .select_from(ValueSetValueMapping)
        .join(source_value, source_value.Id == ValueSetValueMapping.SourceValueId)
        .join(target_value, target_value.Id == ValueSetValueMapping.TargetValueId)
        .join(source_set, source_set.Id == source_value.ValueSetId)
        .join(target_set, target_set.Id == target_value.ValueSetId)
        .where(
            ValueSetValueMapping.Deleted.is_not(True),
            source_set.DataModelId.in_(model_ids),
            target_set.DataModelId.in_(model_ids),
        )
    )
    for source_id, target_id in (await session.execute(pairs)).all():
        content = await _try(export_crosswalk, session, source_id, target_id)
        if content is not None:
            files.append(PortableFile("crosswalk", f"crosswalk {source_id} -> {target_id}", content))
    return files, model_ids


async def _value_set_id(session: AsyncSession, model_ids: dict[tuple, int], side) -> int:
    model = side.Model
    query = select(ValueSet.Id).where(
        ValueSet.DataModelId == model_ids[(model.Name, model.Version, model.ContributorOrganization)],
        ValueSet.Name == side.ValueSet,
        ValueSet.Deleted.is_not(True),
    )
    return (await session.execute(query)).scalar_one()


async def _round_trip(session: AsyncSession, files: list[PortableFile]) -> tuple[list[PortableFile], set[int]]:
    """Import the files into an empty install, commit, and export each again from its new rows."""
    model_ids: dict[tuple, int] = {}
    exports = []
    for file in files:
        if file.kind == "model":
            model_file = parse_model_file(file.content)
            details = model_file.Details
            new_id = await import_model(session, model_file)
            model_ids[(details.Name, details.Version, details.ContributorOrganization)] = new_id
            exports.append((export_model, (new_id,)))
        elif file.kind == "group":
            new_id = await import_mapping_group(session, parse_mapping_group_file(file.content))
            exports.append((export_mapping_group, (new_id,)))
        else:
            crosswalk_file = parse_crosswalk_file(file.content)
            await import_crosswalk(session, crosswalk_file)
            source_id = await _value_set_id(session, model_ids, crosswalk_file.Details.Source)
            target_id = await _value_set_id(session, model_ids, crosswalk_file.Details.Target)
            exports.append((export_crosswalk, (source_id, target_id)))
    await session.commit()

    exported = []
    for file, (export, args) in zip(files, exports):
        exported.append(PortableFile(file.kind, file.label, dump_canonical(await export(session, *args))))
    return exported, set(model_ids.values())


async def test_the_seed_round_trips_into_empty_installs_byte_for_byte(database_url):
    engine, session = await _open(database_url)
    try:
        files_a, source_ids = await _discover(session)
    finally:
        await session.close()
        await engine.dispose()
    assert EXPORTING_MODELS <= source_ids, f"seed models that no longer export: {EXPORTING_MODELS - source_ids}"

    files, installed_ids = files_a, [source_ids]
    for schema in INSTALLS:
        engine, session = await _open(database_url, schema)
        try:
            # Install 2 imports B, not A (§3).
            files, ids = await _round_trip(session, files)
        finally:
            await session.close()
            await engine.dispose()
        for before, after in zip(files_a, files):
            assert after.content == before.content, f"{before.label} changed in {schema}"
        installed_ids.append(ids)

    # The same content under three sets of row Ids, so nothing in a file depended on one.
    source, one, two = installed_ids
    assert source.isdisjoint(one) and source.isdisjoint(two) and one.isdisjoint(two)
