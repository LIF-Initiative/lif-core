import api from "./api";

const apiBaseUrl = import.meta.env.VITE_API_URL;

interface ApiResponse {
  data: any;
}

export interface AttributeParams {
  Name: string;
  DataType: string;
  DataModelId: number;
  UniqueName?: string | null;
  Description?: string | null;
  UseConsiderations?: string | null;
  ValueSetId?: number | null;
  Required?: string | null;
  Array?: string | null;
  SourceModel?: string | null;
  Notes?: string | null;
  CreationDate?: string | null;
  ActivationDate?: string | null;
  DeprecationDate?: string | null;
  Contributor?: string | null;
  ContributorOrganization?: string | null;
  Extension?: boolean;
  ExtensionNotes?: string | null;
  // When set, the API creates the attribute AND its association to this entity in one
  // transaction, so a dropped response can't orphan the attribute (#1028).
  EntityId?: number;
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
}

export const createAttribute = async (params: AttributeParams) => {
  try {
    const result = await api.post<ApiResponse>(`${apiBaseUrl}/attributes/`, params);
    return result.data;
  } catch (error) {
    console.error("Failed to create attribute:", error);
    throw error;
  }
};

export const updateAttribute = async (attributeId: number, params: AttributeParams) => {
  try {
    const result = await api.put<ApiResponse>(`${apiBaseUrl}/attributes/${attributeId}`, params);
    return result.data;
  } catch (error) {
    console.error("Failed to update attribute:", error);
    throw error;
  }
};

export const deleteAttribute = async (attributeId: number) => {
  try {
    const result = await api.delete<ApiResponse>(`${apiBaseUrl}/attributes/${attributeId}`);
    return result.data;
  } catch (error) {
    console.error("Failed to delete attribute:", error);
    throw error;
  }
};

export const deleteEntityAttributeAssociation = async (assocId: number) => {
  try {
    const response = await api.delete<ApiResponse>(
      `${apiBaseUrl}/entity_attribute_associations/${assocId}`
    );
    return response.data;
  } catch (error) {
    console.error("Failed to delete entity attribute association:", error);
    throw error;
  }
};

export const getAttributeEntityAssociationsByAttr = async (
  attributeId: number,
  pagination: boolean = false,
  page: number = 1,
  size: number = 10,
  incExtModelId?: number
) => {
  let url = `${apiBaseUrl}/entity_attribute_associations/by_attribute_id/${attributeId}?pagination=${pagination}`;
  if (pagination) {
    url += `&page=${page}&size=${size}`;
  }
  url += incExtModelId ? `&including_extended_by_data_model_id=${incExtModelId}` : '';

  try {
    const result = await api.get<ApiResponse>(url);
    return result.data.data;
  } catch (error) {
    console.error("Error fetching data:", error);
  }
};

export const getAttributeEntityAssociationsByModel = async (
  modelId: number,
  pagination: boolean = false,
) => {
  const url = `${apiBaseUrl}/entity_attribute_associations/by_data_model_id/${modelId}?pagination=${pagination}`;
  try {
    const result = await api.get<ApiResponse>(url);
    return result.data.data;
  } catch (error) {
    console.error("Error fetching data:", error);
  }
};


export const listAttributesForDataModel = async (dataModelId: number) => {
  const url = `${apiBaseUrl}/attributes/by_data_model_id/${dataModelId}?pagination=false`;
  try {
    const result = await api.get<ApiResponse>(url);
    return result.data.data;
  } catch (error) {
    console.error("Failed to list attributes:", error);
    throw error;
  }
};

export const listAttributesByEntity = async (entityId: number, modelId?: number) => {
  const params = '?pagination=false' + (modelId && modelId > 0 ? `&data_model_id=${modelId}` : '');
  const url = `${apiBaseUrl}/attributes/by_entity_id/${entityId}${params}`;
  try {
    const result = await api.get<ApiResponse>(url);
    return result.data.data || [];
  } catch (error) {
    console.error("Failed to list attributes:", error);
    throw error;
  }
};


export interface CreateEntityAttributeAssociationParams {
  EntityId: number,
  AttributeId: number,
  Notes?: string | null,
  CreationDate?: string | null,
  ActivationDate?: string | null,
  DeprecationDate?: string | null,
  Contributor?: string | null,
  ContributorOrganization?: string | null,
  Extension?: boolean,
  ExtensionNotes?: string | null,
  ExtendedByDataModelId?: number | null,
};
// Generate a template for creating an entity attribute association
export const tmplCreateEntityAttributeAssociation = (parEntityId: number, model: any): CreateEntityAttributeAssociationParams => {
  if (!model?.Id || !model?.Type) console.warn(`templateCreateEntityAttributeAssociation has invalid model: ${model.Id}`);
  const isExt = ["OrgLIF", "PartnerLIF"].includes(model?.Type);
  return {
    EntityId: parEntityId,
    AttributeId: 0,
    CreationDate: new Date().toISOString().slice(0, 16),
    ActivationDate: new Date().toISOString().slice(0, 16),
    Extension: isExt,
    ExtensionNotes: null,
    ExtendedByDataModelId: isExt ? model.Id : undefined,
    Notes: null,
    DeprecationDate: null,
    Contributor: null,
    ContributorOrganization: null,
  };
};

export const createEntityAttributeAssociation = async (params: CreateEntityAttributeAssociationParams) => {
  try {
    const response = await api.post<ApiResponse>(`${apiBaseUrl}/entity_attribute_associations/`, params);
    return response.data;
  } catch (error) {
    console.error("Failed to create entity attribute association:", error);
    throw error;
  }
};

export const updateEntityAttributeAssociation = async (assocId: number, params: Partial<CreateEntityAttributeAssociationParams>) => {
  try {
    const response = await api.put<ApiResponse>(`${apiBaseUrl}/entity_attribute_associations/${assocId}`, params);
    return response.data;
  } catch (error) {
    console.error("Failed to update entity attribute association:", error);
    throw error;
  }
};
