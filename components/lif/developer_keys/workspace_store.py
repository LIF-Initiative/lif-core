"""Workspace-scoped developer keys: the control plane's key store (ADR 0006 decision 3, ADR 0008).

One table holds every workspace's keys, with the workspace as an explicit column, instead of MDR's
per-tenant copies reached through ``search_path``. The workspace is the tenant schema name, kept as
an opaque string: it is stored and compared, never parsed. Checking that the caller belongs to the
workspace is the host's job.

The model is on its own SQLAlchemy registry, so it never shares ``SQLModel.metadata`` with MDR's
``DeveloperApiKey``. Both map a table called ``DeveloperApiKeys``, but in different databases. MDR's
model and functions are unchanged. The table is created by
``projects/lif_control_plane_database/migrations/V1.0__developer_api_keys.sql``.
"""

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy import Column, DateTime, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import registry
from sqlmodel import Field, SQLModel, col, select

from lif.developer_keys.core import _generate_key
from lif.developer_keys.dto import CreatedDeveloperApiKeyDTO, CreateDeveloperApiKeyDTO, DeveloperApiKeyDTO


class _ControlPlaneModel(SQLModel, registry=registry()):
    """Base for the control plane's tables, kept off ``SQLModel.metadata``."""


class WorkspaceDeveloperApiKey(_ControlPlaneModel, table=True):
    """A developer key in the control plane's store. ``KeyHash`` is unique (ADR 0006 decision 3)."""

    __tablename__ = "DeveloperApiKeys"
    Id: Optional[int] = Field(default=None, primary_key=True)
    Workspace: str
    OwnerSub: str
    Label: str
    KeyPrefix: str
    KeyHash: str = Field(unique=True)
    CreationDate: datetime = Field(sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False))
    LastUsedDate: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    RevokedDate: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    ExpirationDate: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))


async def create_workspace_developer_api_key(
    session: AsyncSession, workspace: str, owner_sub: str, data: CreateDeveloperApiKeyDTO
) -> CreatedDeveloperApiKeyDTO:
    raw, key_prefix, key_hash = _generate_key()
    key = WorkspaceDeveloperApiKey(
        Workspace=workspace, OwnerSub=owner_sub, Label=data.Label, KeyPrefix=key_prefix, KeyHash=key_hash
    )
    session.add(key)
    await session.flush()  # INSERT ... RETURNING fills Id and CreationDate
    created = CreatedDeveloperApiKeyDTO(
        Id=key.Id, Label=key.Label, KeyPrefix=key.KeyPrefix, CreationDate=key.CreationDate, Key=raw
    )
    await session.commit()
    return created


async def list_workspace_developer_api_keys(
    session: AsyncSession, workspace: str, owner_sub: str
) -> List[DeveloperApiKeyDTO]:
    """The caller's own keys in one workspace, never the raw key."""
    result = await session.execute(
        select(WorkspaceDeveloperApiKey)
        .where(WorkspaceDeveloperApiKey.Workspace == workspace, WorkspaceDeveloperApiKey.OwnerSub == owner_sub)
        .order_by(col(WorkspaceDeveloperApiKey.Id))
    )
    return [DeveloperApiKeyDTO.model_validate(key) for key in result.scalars().all()]


async def revoke_workspace_developer_api_key(session: AsyncSession, owner_sub: str, key_id: int) -> None:
    """Soft-revoke a key by owner alone, in any workspace (ADR 0008 decision 5).

    A user who has left a workspace's group can still revoke a key they issued there. A key that
    isn't the caller's is a 404, so other users' key ids aren't revealed.
    """
    key = await session.get(WorkspaceDeveloperApiKey, key_id)
    if key is None or key.OwnerSub != owner_sub:
        raise HTTPException(status_code=404, detail="API key not found")
    if key.RevokedDate is None:
        key.RevokedDate = datetime.now(timezone.utc)
        session.add(key)
        await session.commit()
