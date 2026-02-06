import { Node, Edge } from "@xyflow/react";

// Backend enum mirror from service.app.models.DAO.sql_model.StateType
export type StateType =
  | "Published"
  | "Draft"
  | "Work_In_Progress"
  | "Active"
  | "Inactive";

export interface DataModel {
  Id: number;
  Name: string;
  DataModelVersion: string;
  Description: string | null;
  UseConsiderations: string | null;
  Type: string;
  BaseDataModelId: number | null;
  Notes: string | null;
  CreationDate: string | null;
  ActivationDate: string | null;
  DeprecationDate: string | null;
  Contributor: string | null;
  ContributorOrganization: string;
  State: string; // kept broad for compatibility; prefer using StateType where applicable
  Tags: string | null;
  [key: string]: unknown;
}

export interface ModelListProps {
  models: DataModel[];
}

export interface ApiResponse {
  total: number;
  data: DataModel[];
}

export interface ModelDetailsProps {
  model: DataModel;
}

export interface EntitiesListProps {
  dataModelId: number;
  onTotalCount: (count: number) => void;
}

export interface AttributesListProps {
  dataModelId: number;
  onTotalCount: (count: number) => void;
}

export interface EntitiesResponse {
  total: number;
  data: Array<{
    Id: number;
    Name: string;
    UniqueName: string;
    [key: string]: unknown;
  }>;
}

export interface AttributesResponse {
  total: number;
  data: Array<{
    Id: number;
    Name: string;
    [key: string]: unknown;
  }>;
}

export interface EntityAttributes {
  total: number;
  data: Array<{
    Id: number;
    Name: string;
    [key: string]: unknown;
  }>;
}

export interface CountResponse {
  total: number;
  data: Array<{
    Id: number;
    Name: string;
    [key: string]: unknown;
  }>;
}

export type TabType = "details" | "attributes" | "entities";

export interface EntityAssociation {
  ParentEntityId: number;
  ChildEntityId: number;
  Relationship: string | null;
  Placement: string | null;
  Notes: string | null;
  Extension: boolean;
  [key: string]: unknown;
}

export interface EntityNode extends Node {
  data: {
    label: string;
    entityId: number;
  };
}

export interface EntityEdge extends Edge {
  data?: {
    relationship?: string;
  };
}

export interface MDRAny {
  [key: string]: string | number | boolean | null | undefined;
}

export interface RelationshipsProps {
  dataModelId: number;
  selectedEntityId: number | null;
}

// ----- Detailed Data Model (getModelDetails) -----

export interface EntityDTO {
  Id: number;
  Name: string;
  UniqueName: string;
  Description: string | null;
  UseConsiderations: string | null;
  Required: string | null;
  Array: string | null;
  SourceModel: string | null;
  DataModelId: number;
  Notes: string | null;
  CreationDate: string | null;
  ActivationDate: string | null;
  DeprecationDate: string | null;
  Contributor: string | null;
  ContributorOrganization: string | null;
  Extension: boolean;
  ExtensionNotes: string | null;
  Tags?: string | null;
  // New in backend: indicates if this entity is shared/common
  Common?: boolean | null;
}

export interface AttributeDTO {
  Id: number;
  Name: string;
  UniqueName: string;
  Description: string | null;
  UseConsiderations: string | null;
  DataModelId: number;
  DataType: string | null;
  ValueSetId: number | null;
  Required: string | null;
  Array: string | null;
  SourceModel: string | null;
  Notes: string | null;
  CreationDate: string | null;
  ActivationDate: string | null;
  DeprecationDate: string | null;
  Contributor: string | null;
  ContributorOrganization: string | null;
  Extension: boolean;
  ExtensionNotes: string | null;
  // New in backend
  Example?: string | null;
  Common?: boolean | null;
}

export interface EntityWithAttributesDTO {
  Entity: EntityDTO;
  Attributes: AttributeDTO[];
  ParentEntities: EntityDTO[];
  ChildEntities: ChildEntityDTO[];
}

// Matches backend ChildEntityDTO (service.app.models.DTO.entity_dto.ChildEntityDTO)
export interface ChildEntityDTO extends EntityDTO {
  ParentEntityId?: number | null;
  Relationship?: string | null;
  Placement?: string | null;
}

export interface ValueSetDTO {
  Id: number;
  Name: string;
  Description: string | null;
  UseConsiderations: string | null;
  DataModelId: number;
  Notes: string | null;
  CreationDate: string | null;
  ActivationDate: string | null;
  DeprecationDate: string | null;
  Contributor: string | null;
  ContributorOrganization: string | null;
  Extension: boolean;
  ExtensionNotes: string | null;
}

export interface ValueSetValueDTO {
  Id: number;
  ValueSetId: number;
  DataModelId: number;
  Description: string | null;
  UseConsiderations: string | null;
  Value: string;
  ValueName: string | null;
  OriginalValueId: number | null;
  Source: string | null;
  Notes: string | null;
  CreationDate: string | null;
  ActivationDate: string | null;
  DeprecationDate: string | null;
  Contributor: string | null;
  ContributorOrganization: string | null;
  Extension: boolean;
  ExtensionNotes: string | null;
}

export interface ValueSetWithValuesDTO {
  ValueSet: ValueSetDTO;
  Values: ValueSetValueDTO[];
}

export interface TransformationAttributeDTO {
  AttributeId: number;
  EntityId?: number | null;
  AttributeName?: string | null;
  AttributeType: "Source" | "Target" | string;
  Notes?: string | null;
  CreationDate?: string | null;
  ActivationDate?: string | null;
  DeprecationDate?: string | null;
  Contributor?: string | null;
  ContributorOrganization?: string | null;
  // API format: comma-separated numeric IDs, e.g. "654,22,6,-352"
  // Last element is negative when it's an attribute ID (e.g., "-352" means attribute 352)
  // All positive = path ends with entity; negative last = path ends with attribute
  EntityIdPath?: string | null;
}

export interface TransformationDTO {
  Id: number | null;
  TransformationGroupId: number | null;
  Name: string | null;
  Expression: string | null;
  ExpressionLanguage?: string | null;
  Notes: string | null;
  Alignment: string | null;
  CreationDate?: string | null;
  ActivationDate?: string | null;
  DeprecationDate?: string | null;
  Contributor?: string | null;
  ContributorOrganization?: string | null;
  // Deprecated: backend now supports multiple source attributes
  SourceAttribute?: TransformationAttributeDTO | null;
  // New: list of source attributes
  SourceAttributes?: TransformationAttributeDTO[] | null;
  TargetAttribute: TransformationAttributeDTO | null;
}

export interface TransformationListDTO {
  SourceTransformations: TransformationDTO[];
  TargetTransformations: TransformationDTO[];
}

export interface DataModelConstraintDTO {
  Id: number;
  Name: string | null;
  Description: string | null;
  ForDataModelId: number;
  ElementType: "Entity" | "Attribute" | "ValueSet" | string;
  ElementId: number;
  ElementName: string | null;
  ConstraintType: string | null;
  Notes: string | null;
  CreationDate: string | null;
  ActivationDate: string | null;
  DeprecationDate: string | null;
  Contributor: string | null;
  ContributorOrganization: string | null;
  Deleted: boolean;
}

export interface DataModelWithDetailsDTO {
  DataModel: DataModel;
  Entities: EntityWithAttributesDTO[];
  ValueSets: ValueSetWithValuesDTO[];
  Transformations: TransformationListDTO;
  DataModelConstraints: DataModelConstraintDTO[];
}

// ----- Entity Tree (derived client-side) -----
export interface EntityTreeNode {
  // Internal format: dot-separated entity IDs, e.g. "654.22.6"
  // This is converted to API format (comma-separated with negative attr ID) when sending to backend
  PathId: string;
  PathName: string; // e.g. "Parent.Child.Grandchild" (human-readable names)
  EntityId: number;
  // Reference to the original object held in DataModelWithDetailsDTO.Entities (same reference, not a copy)
  Entity: EntityWithAttributesDTO | EntityDTO;
  Children: EntityTreeNode[];
}

export type DataModelWithDetailsWithTree = DataModelWithDetailsDTO & {
  EntityTree: EntityTreeNode[];
};

export interface InclusionDTO {
  Id: number;
  ExtDataModelId: number;
  ElementType: 'Attribute' | 'Entity' | 'Constraint' | 'Transformation' | string;
  IncludedElementId: number;
  CreationDate?: string | null;
  ActivationDate?: string | null;
  DeprecationDate?: string | null;
  Contributor?: string | null;
  ContributorOrganization?: string | null;
  Deleted: boolean;
  LevelOfAccess: 'Private' | 'Public' | 'Internal' | 'Restricted' | string;
}