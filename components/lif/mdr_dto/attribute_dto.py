from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class AttributeDTO(BaseModel):
    Id: Optional[int]
    Name: str
    UniqueName: str
    Description: Optional[str]
    UseConsiderations: Optional[str]
    DataModelId: int
    DataType: Optional[str]
    ValueSetId: Optional[int]
    Required: Optional[str]
    Array: Optional[str]
    SourceModel: Optional[str]
    Notes: Optional[str]
    CreationDate: Optional[datetime]
    ActivationDate: Optional[datetime]
    DeprecationDate: Optional[datetime]
    Contributor: Optional[str]
    ContributorOrganization: Optional[str]
    Extension: bool
    ExtensionNotes: Optional[str]
    Example: Optional[str] = None
    Common: Optional[bool] = None
    # EntityId: Optional[int] = None

    class Config:
        orm_mode = True
        from_attributes = True  # This enables the use of `from_orm`


class CreateAttributeDTO(BaseModel):
    Name: str
    DataType: str
    DataModelId: int
    UniqueName: Optional[str] = None
    Description: Optional[str] = None
    UseConsiderations: Optional[str] = None
    ValueSetId: Optional[int] = None
    Required: Optional[str] = None
    Array: Optional[str] = None
    SourceModel: Optional[str] = None
    Notes: Optional[str] = None
    CreationDate: Optional[datetime] = None
    ActivationDate: Optional[datetime] = None
    DeprecationDate: Optional[datetime] = None
    Contributor: Optional[str] = None
    ContributorOrganization: Optional[str] = None
    Extension: bool = False
    ExtensionNotes: Optional[str] = None
    Example: Optional[str] = None
    Common: Optional[bool] = None
    # When set, the attribute and its association to this entity are created in a single
    # transaction (see create_attribute) so a dropped response can't orphan the attribute (#1028).
    EntityId: Optional[int] = None


class UpdateAttributeDTO(BaseModel):
    Name: Optional[str] = None
    UniqueName: Optional[str] = None
    Description: Optional[str] = None
    UseConsiderations: Optional[str] = None
    DataModelId: Optional[int] = None
    DataType: Optional[str] = None
    ValueSetId: Optional[int] = None
    Required: Optional[str] = None
    Array: Optional[str] = None
    SourceModel: Optional[str] = None
    Notes: Optional[str] = None
    CreationDate: Optional[datetime] = None
    ActivationDate: Optional[datetime] = None
    DeprecationDate: Optional[datetime] = None
    Contributor: Optional[str] = None
    ContributorOrganization: Optional[str] = None
    Extension: Optional[bool] = False
    ExtensionNotes: Optional[str] = None
    Example: Optional[str] = None
    Common: Optional[bool] = None
    # Entity_id: Optional[int] = None


class AttributeWithAssociationMetadataDTO(AttributeDTO):
    EntityAttributeAssociationId: Optional[int] = None
    EntityId: Optional[int] = None
    AssociationNotes: Optional[str] = None
    AssociationCreationDate: Optional[datetime] = None
    AssociationActivationDate: Optional[datetime] = None
    AssociationDeprecationDate: Optional[datetime] = None
    AssociationContributor: Optional[str] = None
    AssociationContributorOrganization: Optional[str] = None
    AssociationExtendedByDataModelId: Optional[int] = None

    # AssociationExtension: Optional[bool] = None
    # AssociationExtensionNotes: Optional[str] = None
    class Config:
        orm_mode = True
        from_attributes = True  # This enables the use of `from_orm`
