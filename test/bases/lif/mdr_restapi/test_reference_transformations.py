"""The portable files in reference_data/transformations/ import into the shipped seed (#1511, #1513).

Each file is imported into both of the seed's schemas, every mapping resolved, and exporting the new
group gives the file back byte for byte. A second import of the same file is refused with GROUP_EXISTS,
which is what lets scripts/import-transformations.sh be re-run. Nothing is committed: each test's
session rolls back.
"""

from pathlib import Path

import pytest
from sqlalchemy import text

from lif.mdr_portability import dump_canonical, parse_mapping_group_file
from lif.mdr_portability.errors import PortabilityErrorCode, PortabilityErrorGroup
from lif.mdr_services.portability_converter import export_mapping_group, import_mapping_group

TRANSFORMATIONS = Path(__file__).resolve().parents[4] / "reference_data" / "transformations"
# Not recursive, like the script: test/ holds a test artifact, not a reference group.
REFERENCE_FILES = sorted(TRANSFORMATIONS.glob("*.json"))
RULES = {
    "Ed-Fi-v5_StateU-LIF__v1.0.json": 83,
    "StateU-LIF_CLR-v2-Open-Badges-v3__v1.0.json": 30,
    "StateU-LIF_Ed-Fi-v5-v1.0__v1.0.json": 70,
}


def test_every_reference_file_is_listed():
    assert {f.name for f in REFERENCE_FILES} == set(RULES)


@pytest.mark.asyncio
@pytest.mark.parametrize("schema", ["public", "tenant_lif_team"])
@pytest.mark.parametrize("path", REFERENCE_FILES, ids=lambda p: p.name)
async def test_reference_file_imports_into_the_seed(test_db_session, schema, path):
    content = path.read_bytes()
    file = parse_mapping_group_file(content)
    assert len(file.Mappings) == RULES[path.name]

    await test_db_session.execute(text(f'SET search_path TO "{schema}", public'))
    group_id = await import_mapping_group(test_db_session, file)
    assert dump_canonical(await export_mapping_group(test_db_session, group_id)) == content

    with pytest.raises(PortabilityErrorGroup) as refused:
        await import_mapping_group(test_db_session, parse_mapping_group_file(content))
    assert [e.code for e in refused.value.exceptions] == [PortabilityErrorCode.GROUP_EXISTS]
    await test_db_session.rollback()
