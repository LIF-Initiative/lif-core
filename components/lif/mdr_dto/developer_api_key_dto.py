from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class CreateDeveloperApiKeyDTO(BaseModel):
    Label: str


class DeveloperApiKeyDTO(BaseModel):
    """Listing view — never includes the raw key."""

    Id: int
    Label: str
    KeyPrefix: str
    CreationDate: datetime
    LastUsedDate: Optional[datetime] = None
    RevokedDate: Optional[datetime] = None

    class Config:
        orm_mode = True
        from_attributes = True


class CreatedDeveloperApiKeyDTO(BaseModel):
    """Create response — includes the raw key, returned exactly once and never again."""

    Id: int
    Label: str
    KeyPrefix: str
    CreationDate: datetime
    Key: str
