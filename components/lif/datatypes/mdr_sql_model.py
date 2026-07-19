from sqlalchemy import Column, DateTime, func
from sqlmodel import SQLModel, Field, Enum as SQLModelEnum
from typing import Optional
from datetime import datetime
from enum import Enum


class DataModelType(str, Enum):
    BaseLIF = "BaseLIF"
    OrgLIF = "OrgLIF"
    SourceSchema = "SourceSchema"
    PartnerLIF = "PartnerLIF"


class ConstraintType(str, Enum):
    IntValueRange = "IntValueRange"
    DoubleValueRange = "DoubleValueRange"
    Length = "Length"
    MaxValue = "MaxValue"
    MinValue = "MinValue"


class TransformationlType(str, Enum):  # cspell:disable-line
    Copy = "Copy"
    Expression = "Expression"


class ExpressionLanguageType(str, Enum):
    JSONata = "JSONata"
    LIF_Pseudo_Code = "LIF_Pseudo_Code"


class AttributeType(str, Enum):
    Source = "Source"
    Target = "Target"


class ElementType(str, Enum):
    Attribute = "Attribute"
    Entity = "Entity"
    Constraint = "Constraint"
    Transformation = "Transformation"


class AccessType(str, Enum):
    Private = "Private"
    Public = "Public"
    Internal = "Internal"
    Restricted = "Restricted"


class StateType(str, Enum):
    Published = "Published"
    Draft = "Draft"
    Work_In_Progress = "Work_In_Progress"
    Active = "Active"
    Inactive = "Inactive"


class EntityPlacementType(str, Enum):
    Embedded = "Embedded"
    Reference = "Reference"


class DatamodelElementType(str, Enum):
    Attribute = "Attribute"
    Entity = "Entity"
    ValueSet = "ValueSet"
    ValueSetValues = "ValueSetValues"
    TransformationsGroup = "TransformationsGroup"
    Transformations = "Transformations"


class DataModel(SQLModel, table=True):
    __tablename__ = "DataModels"
    Id: Optional[int] = Field(default=None, primary_key=True)
    Name: str
    Description: Optional[str]
    UseConsiderations: Optional[str]
    Type: DataModelType = Field(sa_column=SQLModelEnum(DataModelType, name="datamodeltype"))
    BaseDataModelId: Optional[int] = Field(default=None, foreign_key="DataModels.Id")
    Notes: Optional[str]
    DataModelVersion: str
    CreationDate: datetime = Field(sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False))
    ActivationDate: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    DeprecationDate: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    Contributor: Optional[str]
    ContributorOrganization: str
    Deleted: Optional[bool]
    State: Optional[StateType]
    Tags: Optional[str]

    # entities: List["Entity"] = Relationship(back_populates="data_model")


class Entity(SQLModel, table=True):
    __tablename__ = "Entities"
    Id: Optional[int] = Field(default=None, primary_key=True)
    Name: str
    UniqueName: str
    Description: Optional[str]
    UseConsiderations: Optional[str]
    Required: Optional[str]
    Array: Optional[str]
    SourceModel: Optional[str]
    DataModelId: int = Field(foreign_key="DataModels.Id")
    Notes: Optional[str]
    CreationDate: datetime = Field(sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False))
    ActivationDate: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    DeprecationDate: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    Contributor: Optional[str]
    ContributorOrganization: Optional[str]
    Extension: bool = False
    ExtensionNotes: Optional[str]
    Deleted: bool = Field(default=False)
    Tags: Optional[str]
    Common: Optional[bool] = None

    # data_model: Optional["DataModel"] = Relationship(back_populates="entities")


class EntityAssociation(SQLModel, table=True):
    __tablename__ = "EntityAssociation"
    Id: Optional[int] = Field(default=None, primary_key=True)
    ParentEntityId: int = Field(foreign_key="Entities.Id")
    ChildEntityId: int = Field(foreign_key="Entities.Id")
    Relationship: Optional[str]
    Placement: Optional[EntityPlacementType] = Field(
        sa_column=SQLModelEnum(EntityPlacementType, name="entityplacementtype")
    )
    Notes: Optional[str]
    CreationDate: datetime = Field(sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False))
    ActivationDate: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    DeprecationDate: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    Contributor: Optional[str]
    ContributorOrganization: Optional[str]
    Deleted: bool = Field(default=False)
    Extension: bool = False
    ExtensionNotes: Optional[str]
    ExtendedByDataModelId: Optional[int] = Field(foreign_key="DataModels.Id")

    # parent_entity: Optional["Entity"] = Relationship(
    #     sa_relationship_kwargs={"foreign_keys": "[EntityAssociation.ParentEntityId]"}
    # )
    # child_entity: Optional["Entity"] = Relationship(
    #     sa_relationship_kwargs={"foreign_keys": "[EntityAssociation.ChildEntityId]"}
    # )


class ValueSet(SQLModel, table=True):
    __tablename__ = "ValueSets"
    Id: Optional[int] = Field(default=None, primary_key=True)
    Name: str
    Description: Optional[str]
    UseConsiderations: Optional[str]
    DataModelId: int = Field(foreign_key="DataModels.Id")
    Notes: Optional[str]
    CreationDate: datetime = Field(sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False))
    ActivationDate: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    DeprecationDate: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    Contributor: Optional[str]
    ContributorOrganization: Optional[str]
    Extension: bool = Field(default=False)
    ExtensionNotes: Optional[str]
    Deleted: bool = Field(default=False)
    Tags: Optional[str]

    # data_model: Optional["DataModel"] = Relationship(back_populates="value_sets")


class ValueSetValue(SQLModel, table=True):
    __tablename__ = "ValueSetValues"
    Id: Optional[int] = Field(default=None, primary_key=True)
    ValueSetId: int = Field(foreign_key="ValueSets.Id")
    DataModelId: int = Field(foreign_key="DataModels.Id")
    Description: Optional[str]
    UseConsiderations: Optional[str]
    Value: str
    ValueName: Optional[str]
    OriginalValueId: Optional[int] = Field(foreign_key="ValueSetValues.Id")
    Source: Optional[str]
    Notes: Optional[str]
    CreationDate: datetime = Field(sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False))
    ActivationDate: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    DeprecationDate: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    Contributor: Optional[str]
    ContributorOrganization: Optional[str]
    Extension: bool = Field(default=False)
    ExtensionNotes: Optional[str]
    Deleted: bool = Field(default=False)

    # value_set: Optional["ValueSet"] = Relationship(back_populates="values")
    # original_value: Optional["ValueSetValue"] = Relationship(
    #     sa_relationship_kwargs={"foreign_keys": "[ValueSetValue.OriginalValueId]"}
    # )


class Attribute(SQLModel, table=True):
    __tablename__ = "Attributes"
    Id: Optional[int] = Field(default=None, primary_key=True)
    Name: str
    UniqueName: str
    Description: Optional[str]
    UseConsiderations: Optional[str]
    DataModelId: int = Field(foreign_key="DataModels.Id")
    DataType: str
    ValueSetId: Optional[int] = Field(foreign_key="ValueSets.Id")
    Required: Optional[str]
    Array: Optional[str]
    SourceModel: Optional[str]
    Notes: Optional[str]
    CreationDate: datetime = Field(sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False))
    ActivationDate: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    DeprecationDate: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    Contributor: Optional[str]
    ContributorOrganization: Optional[str]
    Extension: bool = Field(default=False)
    ExtensionNotes: Optional[str]
    Deleted: bool = Field(default=False)
    Tags: Optional[str]
    Example: Optional[str] = None
    Common: Optional[bool] = None

    # data_model: Optional["DataModel"] = Relationship(back_populates="attributes")
    # value_set: Optional["ValueSet"] = Relationship(back_populates="attributes")


class EntityAttributeAssociation(SQLModel, table=True):
    __tablename__ = "EntityAttributeAssociation"
    Id: Optional[int] = Field(default=None, primary_key=True)
    EntityId: int = Field(foreign_key="Entities.Id")
    AttributeId: int = Field(foreign_key="Attributes.Id")
    Notes: Optional[str]
    CreationDate: datetime = Field(sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False))
    ActivationDate: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    DeprecationDate: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    Contributor: Optional[str]
    ContributorOrganization: Optional[str]
    Deleted: bool = Field(default=False)
    ExtendedByDataModelId: Optional[int] = Field(foreign_key="DataModels.Id")

    # entity: Optional["Entity"] = Relationship(back_populates="attributes_association")
    # attribute: Optional["Attribute"] = Relationship(back_populates="entities_association")


class Constraint(SQLModel, table=True):
    __tablename__ = "Constraints"
    Id: Optional[int] = Field(default=None, primary_key=True)
    Name: str
    Description: Optional[str]
    UseConsiderations: Optional[str]
    ConstraintType: ConstraintType
    Value: Optional[str]
    AttributeId: int = Field(foreign_key="Attributes.Id")
    Notes: Optional[str]
    CreationDate: datetime = Field(sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False))
    ActivationDate: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    DeprecationDate: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    Contributor: Optional[str]
    ContributorOrganization: Optional[str]
    Deleted: bool = Field(default=False)

    # attribute: Optional["Attribute"] = Relationship(back_populates="constraints")


class DataModelConstraints(SQLModel, table=True):
    __tablename__ = "DataModelConstraints"
    Id: Optional[int] = Field(default=None, primary_key=True)
    Name: Optional[str]
    Description: Optional[str]
    ForDataModelId: int = Field(foreign_key="DataModels.Id")
    ElementType: DatamodelElementType
    ElementId: int
    ConstraintType: Optional[str]
    Notes: Optional[str]
    CreationDate: datetime = Field(sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False))
    ActivationDate: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    DeprecationDate: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    Contributor: Optional[str]
    ContributorOrganization: Optional[str]
    Deleted: bool = Field(default=False)

    # attribute: Optional["Attribute"] = Relationship(back_populates="constraints")


class TransformationGroup(SQLModel, table=True):
    __tablename__ = "TransformationsGroup"
    Id: Optional[int] = Field(default=None, primary_key=True)
    SourceDataModelId: int = Field(foreign_key="DataModels.Id")
    TargetDataModelId: int = Field(foreign_key="DataModels.Id")
    Name: str
    Description: Optional[str]
    GroupVersion: Optional[str]
    Notes: Optional[str]
    CreationDate: datetime = Field(sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False))
    ActivationDate: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    DeprecationDate: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    Contributor: Optional[str]
    ContributorOrganization: Optional[str]
    Deleted: bool = Field(default=False)
    Tags: Optional[str]
    Extension: bool = Field(default=False)
    ExtensionNotes: Optional[str]

    # source_data_model: Optional["DataModel"] = Relationship(
    #     sa_relationship_kwargs={"foreign_keys": "[Transformation.SourceDataModelId]"}
    # )
    # target_data_model: Optional["DataModel"] = Relationship(
    #     sa_relationship_kwargs={"foreign_keys": "[Transformation.TargetDataModelId]"}
    # )


class Transformation(SQLModel, table=True):
    __tablename__ = "Transformations"
    Id: Optional[int] = Field(default=None, primary_key=True)
    # SourceDataModelId: int = Field(foreign_key="DataModels.Id")
    # TargetDataModelId: int = Field(foreign_key="DataModels.Id")
    TransformationGroupId: int = Field(foreign_key="TransformationsGroup.Id")
    Name: str
    Description: Optional[str]
    UseConsiderations: Optional[str]
    Alignment: Optional[str]
    Expression: Optional[str]
    ExpressionLanguage: ExpressionLanguageType = Field(
        # sa_column=ENUM(ExpressionLanguageType, name="expressionlanguagetype", create_type=False),
        sa_column_kwargs={"server_default": "LIF_Pseudo_Code"},  # Default at DB level
        default=ExpressionLanguageType.LIF_Pseudo_Code,
    )
    InputAttributesCount: Optional[int]
    OutputAttributesCount: Optional[int]
    Notes: Optional[str]
    CreationDate: datetime = Field(sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False))
    ActivationDate: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    DeprecationDate: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    Contributor: Optional[str]
    ContributorOrganization: Optional[str]
    Deleted: bool = Field(default=False)
    Extension: bool = Field(default=False)
    ExtensionNotes: Optional[str]

    # source_data_model: Optional["DataModel"] = Relationship(
    #     sa_relationship_kwargs={"foreign_keys": "[Transformation.SourceDataModelId]"}
    # )
    # target_data_model: Optional["DataModel"] = Relationship(
    #     sa_relationship_kwargs={"foreign_keys": "[Transformation.TargetDataModelId]"}
    # )


class TransformationAttribute(SQLModel, table=True):
    __tablename__ = "TransformationAttributes"
    Id: Optional[int] = Field(default=None, primary_key=True)
    EntityId: int = Field(foreign_key="Entities.Id")
    AttributeId: int = Field(foreign_key="Attributes.Id")
    TransformationId: int = Field(foreign_key="Transformations.Id")
    AttributeType: AttributeType  # Should be an Enum, simplified here
    Notes: Optional[str]
    CreationDate: datetime = Field(sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False))
    ActivationDate: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    DeprecationDate: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    Contributor: Optional[str]
    ContributorOrganization: Optional[str]
    Deleted: bool = Field(default=False)
    Extension: bool = Field(default=False)
    ExtensionNotes: Optional[str]
    EntityIdPath: Optional[str] = None

    # attribute: Optional["Attribute"] = Relationship(back_populates="transformation_attributes")
    # transformation: Optional["Transformation"] = Relationship(back_populates="attributes")


class ValueSetValueMapping(SQLModel, table=True):
    __tablename__ = "ValueSetValueMapping"
    Id: Optional[int] = Field(default=None, primary_key=True)
    SourceValueId: int = Field(foreign_key="ValueSetValues.Id")
    TargetValueId: int = Field(foreign_key="ValueSetValues.Id")
    Description: Optional[str]
    UseConsiderations: Optional[str]
    OriginalValueMappingId: Optional[int] = Field(foreign_key="ValueSetValueMapping.Id")
    Notes: Optional[str]
    CreationDate: datetime = Field(sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False))
    ActivationDate: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    DeprecationDate: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    Contributor: Optional[str]
    ContributorOrganization: Optional[str]
    Deleted: bool = Field(default=False)
    TransformationGroupId: Optional[int] = Field(foreign_key="TransformationsGroup.Id")
    SourceValueSetId: Optional[int] = Field(foreign_key="ValueSets.Id")
    TargetValueSetId: Optional[int] = Field(foreign_key="ValueSets.Id")

    # source_value: Optional["ValueSetValue"] = Relationship(
    #     sa_relationship_kwargs={"foreign_keys": "[ValueSetValueMapping.SourceValueId]"}
    # )
    # target_value: Optional["ValueSetValue"] = Relationship(
    #     sa_relationship_kwargs={"foreign_keys": "[ValueSetValueMapping.TargetValueId]"}
    # )
    # original_value_mapping: Optional["ValueSetValueMapping"] = Relationship(
    #     sa_relationship_kwargs={"foreign_keys": "[ValueSetValueMapping.OriginalValueMappingId]"}
    # )


class ExtInclusionsFromBaseDM(SQLModel, table=True):
    __tablename__ = "ExtInclusionsFromBaseDM"
    Id: Optional[int] = Field(default=None, primary_key=True)
    ExtDataModelId: int = Field(foreign_key="DataModels.Id")
    ElementType: ElementType
    IncludedElementId: int
    Notes: Optional[str]
    CreationDate: datetime = Field(sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False))
    ActivationDate: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    DeprecationDate: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    Contributor: Optional[str]
    ContributorOrganization: Optional[str]
    Deleted: bool = Field(default=False)
    LevelOfAccess: AccessType = Field(default=AccessType.Private)
    Queryable: bool = Field(default=False)
    Modifiable: bool = Field(default=False)

    # ext_data_model: Optional["DataModel"] = Relationship(back_populates="ext_inclusions")


class ExtMappedValueSet(SQLModel, table=True):
    __tablename__ = "ExtMappedValueSet"
    Id: Optional[int] = Field(default=None, primary_key=True)
    ValueSetId: int = Field(foreign_key="ValueSets.Id")
    MappedValueSetId: int = Field(foreign_key="ValueSets.Id")
    Description: Optional[str]
    UseConsiderations: Optional[str]
    Notes: Optional[str]
    CreationDate: datetime = Field(sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False))
    ActivationDate: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    DeprecationDate: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    Contributor: Optional[str]
    ContributorOrganization: Optional[str]
    Deleted: bool = Field(default=False)

    # value_set: Optional["ValueSet"] = Relationship(
    #     sa_relationship_kwargs={"foreign_keys": "[ExtMappedValueSet.ValueSetId]"}
    # )
    # mapped_value_set: Optional["ValueSet"] = Relationship(
    #     sa_relationship_kwargs={"foreign_keys": "[ExtMappedValueSet.MappedValueSetId]"}
    # )


class DeveloperApiKey(SQLModel, table=True):
    """User-owned API key for programmatic access to the LDE /exports API (#1033).

    Lives in the tenant schema (workspace-scoped via search_path) and is further scoped to a
    user by OwnerSub (the Cognito `sub`). The raw key is returned to the caller exactly once
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
