from typing import List
from sqlalchemy import select
from sqlalchemy.orm import Session
from lif.identity_mapper_storage_sql.model import IdentityMappingModel


def create(session: Session, model: IdentityMappingModel) -> IdentityMappingModel:
    session.add(model)
    session.flush()
    return model


def read(session: Session, mapping_id: str) -> IdentityMappingModel | None:
    query = select(IdentityMappingModel).where(IdentityMappingModel.mapping_id == mapping_id)
    return session.execute(query).scalar()


def read_by_lif_org_and_person(
    session: Session, lif_organization_id: str, lif_organization_person_id: str
) -> List[IdentityMappingModel]:
    query = select(IdentityMappingModel).where(
        IdentityMappingModel.lif_organization_id == lif_organization_id,
        IdentityMappingModel.lif_organization_person_id == lif_organization_person_id,
    )
    return list(session.execute(query).scalars().all())


def delete(session: Session, existing: IdentityMappingModel) -> None:
    session.delete(existing)
