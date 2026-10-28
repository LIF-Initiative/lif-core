"""Postgres-backed checks that an overlay's attribute list comes from its own inclusion rows (issue #1431).

On the seed, attribute 800 (Credential.expirationDate) is included only in model 17, and attribute 1290
(Common.Identifier.identifier) is Private in model 17 but Public in model 18. Both overlays use model 1
as their base, so both see both attributes' associations.
"""

from lif.mdr_services.attribute_service import get_list_of_attributes_for_entity
from lif.mdr_services.datamodel_service import get_datamodel_with_details_by_id
from lif.mdr_sql_model.core import DataModelType

STATEU, ORG2 = 17, 18
TYPES = {STATEU: DataModelType.OrgLIF, ORG2: DataModelType.PartnerLIF}
CREDENTIAL, IDENTIFIER = 129, 238
EXPIRATION_DATE, IDENTIFIER_ATTRIBUTE = 800, 1290


async def _attribute_ids(session, entity_id: int, model_id: int, public_only: bool = False) -> list[int]:
    _, attributes = await get_list_of_attributes_for_entity(
        session, entity_id, model_id, data_model_type=TYPES[model_id], pagination=False, public_only=public_only
    )
    return [attribute.Id for attribute in attributes]


async def test_an_attribute_included_in_one_overlay_is_not_in_another(test_db_session):
    assert EXPIRATION_DATE in await _attribute_ids(test_db_session, CREDENTIAL, STATEU)
    assert EXPIRATION_DATE not in await _attribute_ids(test_db_session, CREDENTIAL, ORG2)


async def test_public_only_reads_the_overlays_own_inclusion_row(test_db_session):
    assert IDENTIFIER_ATTRIBUTE in await _attribute_ids(test_db_session, IDENTIFIER, ORG2, public_only=True)
    assert IDENTIFIER_ATTRIBUTE in await _attribute_ids(test_db_session, IDENTIFIER, STATEU)
    assert IDENTIFIER_ATTRIBUTE not in await _attribute_ids(test_db_session, IDENTIFIER, STATEU, public_only=True)


async def test_with_details_lists_only_the_overlays_own_attributes(test_db_session):
    details = await get_datamodel_with_details_by_id(test_db_session, ORG2)
    attribute_ids = {attribute.Id for entity in details.Entities for attribute in entity.Attributes}
    assert EXPIRATION_DATE not in attribute_ids
