from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from lif.mdr_sql_model.core import AccessType, ElementType


class InclusionDTO(BaseModel):
    Id: Optional[int]
    ExtDataModelId: int
    ElementType: "ElementType"
    IncludedElementId: int
    Notes: Optional[str] = None
    CreationDate: Optional[datetime] = None
    ActivationDate: Optional[datetime] = None
    DeprecationDate: Optional[datetime] = None
    Contributor: Optional[str] = None
    ContributorOrganization: Optional[str] = None
    Deleted: bool
    LevelOfAccess: AccessType
    Queryable: Optional[bool] = False
    Modifiable: Optional[bool] = False

    class Config:
        orm_mode = True
        from_attributes = True  # This enables the use of `from_orm`


class CreateInclusionDTO(BaseModel):
    ExtDataModelId: int
    ElementType: ElementType
    IncludedElementId: int
    Notes: Optional[str] = None
    CreationDate: datetime
    ActivationDate: Optional[datetime] = None
    DeprecationDate: Optional[datetime] = None
    Contributor: Optional[str] = None
    ContributorOrganization: Optional[str] = None
    Deleted: Optional[bool] = False
    LevelOfAccess: AccessType
    Queryable: Optional[bool] = False
    Modifiable: Optional[bool] = False


class UpdateInclusionDTO(BaseModel):
    Notes: Optional[str] = None
    ActivationDate: Optional[datetime] = None
    DeprecationDate: Optional[datetime] = None
    Contributor: Optional[str] = None
    ContributorOrganization: Optional[str] = None
    LevelOfAccess: Optional[AccessType] = None
    Queryable: Optional[bool] = None
    Modifiable: Optional[bool] = None
