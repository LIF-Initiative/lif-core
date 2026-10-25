"""Tests for the #1388 read-only count of what converting each overlay model would touch.

The counts size a data conversion of the model every deployed service loads, so a wrong count
misleads its design. The seed test pins the figures for models 17 and 18 in backup.sql, which agree
with the spec's §11 inventory (docs/specs/mdr-portable-file-format.md). It needs a local PostgreSQL
(`initdb` and `psql`) and skips without one, like the MDR tests.
"""

import importlib.util
import os
import pathlib
import subprocess
from urllib.parse import urlparse

import asyncpg
import pytest
import testing.postgresql

_ROOT = pathlib.Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "measure_overlay_conversion", _ROOT / "scripts" / "measure_overlay_conversion.py"
)
measure = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(measure)


def _inclusion(kind, element_id, owner, name, deleted=False, value_set=None):
    return {
        "ElementType": kind,
        "ElementId": element_id,
        "OwnerId": owner,
        "ElementDeleted": deleted,
        "UniqueName": name,
        "ValueSetId": value_set,
    }


def _own(kind, name, value_set_model=None, associated=True):
    return {"ElementType": kind, "UniqueName": name, "ValueSetModelId": value_set_model, "Associated": associated}


def test_measure_model_counts_a_repeated_inclusion_row_once():
    # Seed model 18 includes attribute 1291 twice; that is one element to copy, not a clash.
    result = measure.measure_model(
        18,
        1,
        [
            _inclusion("Attribute", 1291, 1, "Common.Identifier.identifierType", value_set=7),
            _inclusion("Attribute", 1291, 1, "Common.Identifier.identifierType", value_set=7),
            _inclusion("Attribute", 900, None, None),
            _inclusion("Entity", 5, 18, "Own"),
        ],
        [_own("Entity", "Own")],
        [],
    )
    assert result["incl foreign"] == "0/2"
    assert result["incl absent"] == "0/1"
    assert result["incl own"] == "1/0"
    assert result["dup incl"] == 1
    assert result["clashes"] == 0
    assert result["vs to copy"] == 1


def test_measure_model_tells_an_override_from_a_clash():
    result = measure.measure_model(
        17,
        1,
        # image.id comes from model 16, which is not the base: copying it in makes a second image.id.
        [_inclusion("Attribute", 1745, 16, "image.id")],
        [
            _own("Attribute", "image.id"),
            _own("Attribute", "Criteria.identifier"),
            _own("Attribute", "Common.Contact.Address.addressState", value_set_model=1),
            _own("Attribute", "Credential.schemaType", associated=False),
        ],
        # Criteria.identifier also exists in the base model but is not included: an override.
        [{"ElementType": "Attribute", "UniqueName": "Criteria.identifier"}],
    )
    assert result["override names"] == [("Attribute", "Criteria.identifier")]
    assert result["clash names"] == [("Attribute", "image.id")]
    assert result["vs foreign"] == 1
    assert result["unassociated"] == 1


@pytest.fixture(scope="module")
def seed_url():
    try:
        postgresql = testing.postgresql.Postgresql()
    except RuntimeError as e:
        pytest.skip(f"PostgreSQL not available locally: {e}")
    with postgresql:
        url = urlparse(postgresql.url())
        result = subprocess.run(
            [
                "psql",
                "-h",
                url.hostname,
                "-p",
                str(url.port),
                "-U",
                url.username,
                "-d",
                url.path.lstrip("/"),
                "-f",
                str(_ROOT / "projects/lif_mdr_database/backup.sql"),
            ],
            env={**os.environ, "PGPASSWORD": url.password or ""},
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            pytest.fail(f"Failed to load backup.sql: {result.stderr}")
        yield postgresql.url()


async def test_measure_reports_the_seed_overlays_in_every_schema(seed_url):
    conn = await asyncpg.connect(seed_url)
    try:
        results = await measure.measure(conn)
    finally:
        await conn.close()

    assert list(results) == ["public", "tenant_lif_team"]
    for schema, (models, other_extended) in results.items():
        rows = {row["model"]: {c: row[c] for c in measure.COLUMNS if c != "schema"} for row in models}
        assert rows == {
            "17 StateU LIF": {
                "model": "17 StateU LIF",
                "type": "OrgLIF",
                "base": 1,
                "incl own": "11/51",
                "incl foreign": "25/114",
                "incl absent": "1/4",
                "dup incl": 0,
                "overrides": 1,
                "clashes": 1,
                "vs foreign": 1,
                "vs to copy": 0,
                "extended by": "15/150",
                "unassociated": 14,
                "groups": 6,
                "rules": 5,
                "mapping rows": 10,
            },
            "18 Org2 LIF": {
                "model": "18 Org2 LIF",
                "type": "PartnerLIF",
                "base": 1,
                "incl own": "10/11",
                "incl foreign": "13/55",
                "incl absent": "0/5",
                "dup incl": 1,
                "overrides": 0,
                "clashes": 0,
                "vs foreign": 0,
                "vs to copy": 2,
                "extended by": "1/15",
                "unassociated": 0,
                "groups": 0,
                "rules": 0,
                "mapping rows": 0,
            },
        }, schema
        assert [row["override names"] for row in models] == [[("Attribute", "Criteria.identifier")], []]
        assert [row["clash names"] for row in models] == [[("Attribute", "image.id")], []]
        # Model 25 is a source model, not an overlay, yet declares two ExtendedBy attribute links.
        assert {m: measure._pair(c) for m, c in other_extended.items()} == {25: "0/2"}
