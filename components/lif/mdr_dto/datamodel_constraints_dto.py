from typing import Optional
from pydantic import BaseModel


from datetime import datetime

from lif.mdr_sql_model.core import DatamodelElementType


class DataModelConstraintsDTO(BaseModel):
    Id: Optional[int]
    Name: Optional[str] = None
    Description: Optional[str] = None
    ForDataModelId: int
    ElementType: DatamodelElementType
    ElementId: int
    ElementName: Optional[str] = None
    ConstraintType: Optional[str] = None
    Notes: Optional[str] = None
    CreationDate: Optional[datetime] = None
    ActivationDate: Optional[datetime] = None
    DeprecationDate: Optional[datetime] = None
    Contributor: Optional[str]
    ContributorOrganization: Optional[str]
    Deleted: Optional[bool] = False

    class Config:
        orm_mode = True  # This allows Pydantic to work with SQLModel/ORM objects
        from_attributes = True  # This enables the use of `from_orm`


class CreateDataModelConstraintsDTO(BaseModel):
    Name: Optional[str] = None
    Description: Optional[str] = None
    ForDataModelId: int
    ElementType: DatamodelElementType
    ElementId: int
    ConstraintType: Optional[str] = None
    Notes: Optional[str] = None
    CreationDate: Optional[datetime] = None
    ActivationDate: Optional[datetime] = None
    DeprecationDate: Optional[datetime] = None
    Contributor: str
    ContributorOrganization: str
    Deleted: Optional[bool] = False


class UpdateDataModelConstraintsDTO(BaseModel):
    Name: Optional[str] = None
    Description: Optional[str] = None
    ForDataModelId: Optional[int] = None
    ElementType: Optional[DatamodelElementType] = None
    ElementId: Optional[int] = None
    ConstraintType: Optional[str] = None
    Notes: Optional[str] = None
    CreationDate: Optional[datetime] = None
    ActivationDate: Optional[datetime] = None
    DeprecationDate: Optional[datetime] = None
    Contributor: Optional[str] = None
    ContributorOrganization: Optional[str] = None
    Deleted: Optional[bool] = False

    class Config:
        orm_mode = True  # This allows Pydantic to work with SQLModel/ORM objects
        from_attributes = True  # This enables the use of `from_orm`
