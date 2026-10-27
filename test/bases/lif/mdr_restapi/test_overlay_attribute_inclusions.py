"""Postgres-backed checks that an overlay's attributes come from its own inclusion rows (issue #1428).

On the seed, attribute 800 (Credential.expirationDate) is included only in model 17, and attribute 1290
(Common.Identifier.identifier) is Private in model 17 but Public in model 18. Both overlays use model 1
as their base, so both see both attributes' associations.
"""

import pytest

from lif.mdr_services.attribute_service import get_attributes_with_association_metadata_for_entity
from lif.mdr_services.schema_generation_service import generate_openapi_schema
from lif.mdr_sql_model.core import DataModelType

STATEU, ORG2 = 17, 18
TYPES = {STATEU: DataModelType.OrgLIF, ORG2: DataModelType.PartnerLIF}
CREDENTIAL, IDENTIFIER = 129, 238
EXPIRATION_DATE, IDENTIFIER_ATTRIBUTE = 800, 1290


async def _attribute_ids(session, entity_id: int, model_id: int, public_only: bool = False) -> set[int]:
    attributes = await get_attributes_with_association_metadata_for_entity(
        session, entity_id, model_id, data_model_type=TYPES[model_id], public_only=public_only
    )
    return {attribute.Id for attribute in attributes}


async def test_an_attribute_included_in_one_overlay_is_not_in_another(test_db_session):
    assert EXPIRATION_DATE in await _attribute_ids(test_db_session, CREDENTIAL, STATEU)
    assert EXPIRATION_DATE not in await _attribute_ids(test_db_session, CREDENTIAL, ORG2)


async def test_public_only_reads_the_overlays_own_inclusion_row(test_db_session):
    assert IDENTIFIER_ATTRIBUTE in await _attribute_ids(test_db_session, IDENTIFIER, ORG2, public_only=True)
    assert IDENTIFIER_ATTRIBUTE in await _attribute_ids(test_db_session, IDENTIFIER, STATEU)
    assert IDENTIFIER_ATTRIBUTE not in await _attribute_ids(test_db_session, IDENTIFIER, STATEU, public_only=True)


@pytest.mark.parametrize("model_id, public_only", [(ORG2, False), (ORG2, True), (STATEU, True)])
async def test_overlays_generate_with_attributes(test_db_session, model_id, public_only):
    # These combinations used to 404 on another overlay's inclusion row.
    schema = await generate_openapi_schema(
        test_db_session, model_id, include_attr_md=True, include_entity_md=False, public_only=public_only
    )
    assert schema["components"]["schemas"]
