"""Generated-schema snapshots for every live seed model (Issue #1387).

ADR data_model/0004 accepts a model conversion only if the MDR generates the same
schema for it before and after. These tests pin what generate_openapi_schema returns
today -- JSON-encoded the way the /datamodels/open_api_schema endpoint encodes it --
for every non-deleted model in projects/lif_mdr_database/backup.sql, across all 16
combinations of include_attr_md / include_entity_md / public_only / full_export.

Fixtures live in schema_snapshots/: manifest.json maps model -> flag combination ->
schema file, and identical outputs share one file under schemas/.

To regenerate after an intended change (the run fails on purpose; review the diff):

    LIF_UPDATE_SCHEMA_SNAPSHOTS=1 uv run pytest test/bases/lif/mdr_restapi/test_schema_snapshots.py
"""

import difflib
import hashlib
import itertools
import json
import os
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import text

from lif.mdr_services.schema_generation_service import generate_openapi_schema

SNAPSHOT_DIR = Path(__file__).parent / "schema_snapshots"
MANIFEST_PATH = SNAPSHOT_DIR / "manifest.json"
SCHEMAS_DIR = SNAPSHOT_DIR / "schemas"
UPDATE = os.getenv("LIF_UPDATE_SCHEMA_SNAPSHOTS") == "1"

FLAG_NAMES = ("include_attr_md", "include_entity_md", "public_only", "full_export")
FLAG_MATRIX = [dict(zip(FLAG_NAMES, values)) for values in itertools.product([False, True], repeat=4)]


def _flag_key(flags: dict) -> str:
    return "attr{:d}-entity{:d}-public{:d}-full{:d}".format(*(flags[name] for name in FLAG_NAMES))


def _canonical(schema) -> str:
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text())


def _manifest_model_ids() -> list[int]:
    if not MANIFEST_PATH.exists():
        return []
    return sorted(int(model_id) for model_id in _load_manifest())


async def _live_models(session) -> list[tuple[int, str, str]]:
    result = await session.execute(
        text('SELECT "Id", "Name", "Type" FROM "DataModels" WHERE "Deleted" = false ORDER BY "Id"')
    )
    return [tuple(row) for row in result.fetchall()]


async def _generate(session, data_model_id: int, flags: dict):
    # Expunge between calls so entity __dict__ copies (include_entity_md) never
    # carry state loaded by an earlier combination.
    session.expunge_all()
    try:
        return jsonable_encoder(await generate_openapi_schema(session, data_model_id, **flags))
    except HTTPException as e:
        # Some combinations fail today (e.g. a missing inclusion row on an overlay
        # model); the endpoint returns that error, so it is part of the baseline.
        return {"x-snapshot-http-error": {"status_code": e.status_code, "detail": e.detail}}


def _diff_excerpt(expected: str, actual: str, limit: int = 40) -> str:
    lines = list(difflib.unified_diff(expected.splitlines(), actual.splitlines(), "snapshot", "generated", lineterm=""))
    more = f"\n... {len(lines) - limit} more diff lines" if len(lines) > limit else ""
    return "\n".join(lines[:limit]) + more


@pytest.mark.skipif(not UPDATE, reason="set LIF_UPDATE_SCHEMA_SNAPSHOTS=1 to regenerate the snapshots")
async def test_regenerate_schema_snapshots(seed_db_session):
    assert not os.getenv("CI"), "Schema snapshots must be regenerated locally and committed, never in CI"

    manifest = {}
    blobs = {}
    for data_model_id, name, model_type in await _live_models(seed_db_session):
        schemas = {}
        for flags in FLAG_MATRIX:
            canonical = _canonical(await _generate(seed_db_session, data_model_id, flags))
            blob_name = hashlib.sha256(canonical.encode()).hexdigest()[:12] + ".json"
            blobs[blob_name] = canonical
            schemas[_flag_key(flags)] = blob_name
        manifest[str(data_model_id)] = {"name": name, "type": model_type, "schemas": schemas}

    SCHEMAS_DIR.mkdir(parents=True, exist_ok=True)
    for stale in SCHEMAS_DIR.glob("*.json"):
        if stale.name not in blobs:
            stale.unlink()
    for blob_name, canonical in blobs.items():
        (SCHEMAS_DIR / blob_name).write_text(canonical)
    MANIFEST_PATH.write_text(_canonical(manifest))

    pytest.fail(
        f"Schema snapshots regenerated ({len(manifest)} models, {len(blobs)} distinct schemas). "
        "Review the diff, then re-run without LIF_UPDATE_SCHEMA_SNAPSHOTS."
    )


@pytest.mark.skipif(UPDATE, reason="regenerating snapshots")
async def test_snapshots_cover_every_live_seed_model(seed_db_session):
    live = {str(data_model_id) for data_model_id, _, _ in await _live_models(seed_db_session)}
    assert live == set(_load_manifest()), (
        "Live models in backup.sql and the schema snapshots differ; regenerate with LIF_UPDATE_SCHEMA_SNAPSHOTS=1"
    )


@pytest.mark.skipif(UPDATE, reason="regenerating snapshots")
@pytest.mark.parametrize("data_model_id", _manifest_model_ids())
async def test_generated_schema_matches_snapshot(seed_db_session, data_model_id):
    entry = _load_manifest()[str(data_model_id)]
    assert set(entry["schemas"]) == {_flag_key(flags) for flags in FLAG_MATRIX}

    failures = []
    for flags in FLAG_MATRIX:
        key = _flag_key(flags)
        expected = (SCHEMAS_DIR / entry["schemas"][key]).read_text()
        actual = await _generate(seed_db_session, data_model_id, flags)
        if actual != json.loads(expected):
            failures.append(f"--- {key}\n{_diff_excerpt(expected, _canonical(actual))}")

    assert not failures, (
        f"Generated schema for model {data_model_id} ({entry['name']}) changed in "
        f"{len(failures)}/{len(FLAG_MATRIX)} flag combinations. If intended, regenerate with "
        "LIF_UPDATE_SCHEMA_SNAPSHOTS=1.\n\n" + "\n\n".join(failures)
    )
