"""Helpers the portability converters share (issue #1430).

model_converter, mapping_group_converter and crosswalk_converter all use these, so they live here
rather than as one converter's private names.
"""

from datetime import datetime
from typing import Any, Optional

from lif.mdr_portability.v1.models import ModelIdentity
from lif.mdr_sql_model.core import DataModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select


def without_nulls(item: Any) -> Any:
    # Optional fields are left out when NULL, as the canonical form writes them (§9).
    if isinstance(item, dict):
        return {key: without_nulls(value) for key, value in item.items() if value is not None}
    if isinstance(item, list):
        return [without_nulls(entry) for entry in item]
    return item


def to_json(value: Any) -> str:
    # Stored timestamps are timezone-aware, so isoformat writes an RFC 3339 offset (§9).
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"{type(value).__name__} is not JSON serializable")


async def find_model(session: AsyncSession, identity: ModelIdentity) -> Optional[DataModel]:
    return (
        (
            await session.execute(
                select(DataModel).where(
                    DataModel.Name == identity.Name,
                    DataModel.DataModelVersion == identity.Version,
                    DataModel.ContributorOrganization == identity.ContributorOrganization,
                    DataModel.Deleted.is_not(True),
                )
            )
        )
        .scalars()
        .first()
    )
