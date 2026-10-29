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


def _association(kind, association_id, extended_by, parent, parent_model, child, child_model):
    return {
        "ElementType": kind,
        "Id": association_id,
        "ExtendedByDataModelId": extended_by,
        "ParentId": parent,
        "ParentModelId": parent_model,
        "ChildId": child,
        "ChildModelId": child_model,
    }


def _mapping_row(path, entity=None, attribute=None):
    return {"Id": 1, "EntityId": entity, "AttributeId": attribute, "EntityIdPath": path}


def test_check_model_sorts_extended_by_rows_by_where_their_ends_are():
    # Model 17 on base 1 shows entities 132 (model 1) and 40 (own), and attributes 1745 (model 16) and 7 (model 1).
    inclusions = [
        _inclusion("Entity", 132, 1, "Credential"),
        _inclusion("Entity", 40, 17, "Own"),
        _inclusion("Attribute", 1745, 16, "image.id"),
        _inclusion("Attribute", 7, 1, "Credential.name"),
    ]
    associations = [
        _association("Entity", 1, 17, 132, 1, 133, 1),  # both ends in the base
        _association("Attribute", 2, 17, 40, 17, 7, 1),  # an end in the model
        _association("Attribute", 3, 17, 900, 16, 901, 16),  # both ends in model 16, not shown
        _association("Attribute", 4, 17, 132, 1, 1745, 16),  # ends in two other models, shown: like 1846
        _association("Attribute", 5, 17, 132, 1, 999, None),  # soft-deleted end
        _association("Attribute", 6, 18, 132, 1, 7, 1),  # another overlay's row inside this render set
        _association("Attribute", 7, 18, 132, 1, 8, 1),  # another overlay's row, attribute 8 not shown
        _association("Attribute", 8, 25, 132, 1, 7, 1),  # a non-overlay's row is not cross-overlay
        _association("Attribute", 9, None, 132, 1, 41, 17),  # no ExtendedBy, base entity -> own attribute
        _association("Attribute", 10, None, 132, 1, 902, 16),  # no ExtendedBy, but no end in this model
    ]
    result = measure.check_model(17, 1, {17, 18}, inclusions, associations, [])
    assert {k: v for k, v in result.items() if k.startswith(("ext ", "cross"))} == {
        "ext base": "1/0",
        "ext own": "0/1",
        "ext other": "0/1",
        "ext other shown": "0/0",
        "ext no owner": "0/1",
        "ext no owner shown": "0/1",
        "ext absent": "0/1",
        "ext null cross": "0/1",
        "cross overlay": "0/1",
    }
    assert [row["Id"] for row in result["no owner rows"]] == [4]
    assert [row["Id"] for row in result["null cross rows"]] == [9]


def test_check_model_finds_mapping_nodes_outside_the_render_set():
    inclusions = [
        _inclusion("Entity", 10, 1, "A"),
        _inclusion("Entity", 11, 1, "A.B"),
        _inclusion("Attribute", 20, 1, "A.B.c"),
        _inclusion("Attribute", 21, 1, "A.d", deleted=True),
    ]
    rows = [
        _mapping_row("10,11,-20"),  # inside
        _mapping_row("10,12,-20"),  # entity 12 is not included
        _mapping_row("10,-21"),  # attribute 21 is soft-deleted, so absent
        _mapping_row(None, entity=10, attribute=20),  # no path: its own entity and attribute, inside
        _mapping_row("10,x,-20"),  # not a list of IDs
    ]
    result = measure.check_model(17, 1, {17}, inclusions, [], rows)
    assert (result["paths outside"], result["paths invalid"]) == (2, 1)


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
        checks = {
            row["model"]: {c: row[c] for c in measure.CHECK_COLUMNS if c not in ("schema", "model")} for row in models
        }
        # 17's 15/150 ExtendedBy rows: 13/75 own an end, 0/59 lie in model 16, 0/1 (association 1846) has no
        # owner, and 2/15 have a soft-deleted end. 18's 0/1 lies in model 25. None of the other-model rows is
        # shown, so the conversion copies none of them (#1388).
        assert checks == {
            "17 StateU LIF": {
                "odd types": "0/0/0",
                "flag conflicts": 0,
                "ext base": "0/0",
                "ext own": "13/75",
                "ext other": "0/59",
                "ext other shown": "0/0",
                "ext no owner": "0/1",
                "ext no owner shown": "0/1",
                "ext absent": "2/15",
                "ext null cross": "0/8",
                "cross overlay": "0/0",
                "paths outside": 0,
                "paths invalid": 0,
            },
            "18 Org2 LIF": {
                "odd types": "0/0/0",
                "flag conflicts": 0,
                "ext base": "0/0",
                "ext own": "1/14",
                "ext other": "0/1",
                "ext other shown": "0/0",
                "ext no owner": "0/0",
                "ext no owner shown": "0/0",
                "ext absent": "0/0",
                "ext null cross": "0/0",
                "cross overlay": "0/0",
                "paths outside": 0,
                "paths invalid": 0,
            },
        }, schema
        assert [
            [
                (a["Id"], a["ParentId"], a["ParentModelId"], a["ChildId"], a["ChildModelId"])
                for a in row["no owner rows"]
            ]
            for row in models
        ] == [[(1846, 132, 1, 1745, 16)], []]
        # Model 1's own associations, with no ExtendedBy, to attributes model 17 owns. Model 1's schema shows them.
        assert [
            [(a["Id"], a["ParentModelId"], a["ChildModelId"]) for a in row["null cross rows"]] for row in models
        ] == [[(i, 1, 17) for i in (1263, 1282, 1284, 1285, 1286, 1288, 1315, 1619)], []]
        # Model 25 is a source model, not an overlay, yet declares two ExtendedBy attribute links.
        assert {m: measure._pair(c) for m, c in other_extended.items()} == {25: "0/2"}
