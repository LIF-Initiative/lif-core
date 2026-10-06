from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, func
from sqlmodel import Field, SQLModel


class DeveloperApiKey(SQLModel, table=True):
    """User-owned API key for programmatic access to the LDE /exports API (#1033).

    Workspace scoping is the host's job: today MDR reaches this table in the request's tenant
    schema via search_path (ADR 0006). Within a workspace, keys are scoped to a user by OwnerSub
    (the Cognito `sub`). The raw key is returned to the caller exactly once
    on creation and never stored — only its SHA-256 hash (KeyHash) plus a display prefix.
    """

    __tablename__ = "DeveloperApiKeys"
    Id: Optional[int] = Field(default=None, primary_key=True)
    OwnerSub: str = Field(index=True)
    Label: str
    KeyPrefix: str
    KeyHash: str = Field(index=True)
    CreationDate: datetime = Field(sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False))
    LastUsedDate: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    RevokedDate: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    ExpirationDate: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
