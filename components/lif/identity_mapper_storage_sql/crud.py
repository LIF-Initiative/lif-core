from typing import List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from lif.identity_mapper_storage_sql.model import IdentityMappingModel


async def create(session: AsyncSession, model: IdentityMappingModel) -> IdentityMappingModel:
    session.add(model)
    await session.flush()
    return model


async def create_all(session: AsyncSession, models: List[IdentityMappingModel]) -> List[IdentityMappingModel]:
    """Add many models without flushing each one; the caller flushes once."""
    session.add_all(models)
    return models


async def read(session: AsyncSession, mapping_id: str) -> IdentityMappingModel | None:
    query = select(IdentityMappingModel).where(IdentityMappingModel.mapping_id == mapping_id)
    result = await session.execute(query)
    return result.scalar()


async def read_by_lif_org_and_person(
    session: AsyncSession, lif_organization_id: str, lif_organization_person_id: str
) -> List[IdentityMappingModel]:
    query = select(IdentityMappingModel).where(
        IdentityMappingModel.lif_organization_id == lif_organization_id,
        IdentityMappingModel.lif_organization_person_id == lif_organization_person_id,
    )
    result = await session.execute(query)
    return list(result.scalars().all())


async def delete(session: AsyncSession, existing: IdentityMappingModel) -> None:
    await session.delete(existing)
