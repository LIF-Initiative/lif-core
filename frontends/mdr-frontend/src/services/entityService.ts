import api from "./api";
import { isOverlayModel } from "../utils/modelUtils";

const apiBaseUrl = import.meta.env.VITE_API_URL;

interface ApiResponse {
  data: any;
}

export const listEntities = async (pagination = false, page = 1, size = 10) => {
  try {
    let url = `${apiBaseUrl}/entities/?pagination=${pagination}`;
    if (pagination) {
      url += `&page=${page}&size=${size}`;
    }
    const result = await api.get<ApiResponse>(url);
    return result.data.data;
  } catch (error) {
    console.error("Error fetching data:", error);
  }
};

export const getEntity = async (id: string) => {
  try {
    const result = await api.get<ApiResponse>(`${apiBaseUrl}/entities/${id}`);
    return result.data;
  } catch (error) {
    console.error("Error fetching data:", error);
  }
};

export const getEntities = async (ids: number[]) => {
  try {
    const url = `${apiBaseUrl}/entities/entities/by_ids/?${ids
      .map((id) => `ids=${id}`)
      .join("&")}`;
    const result = await api.get(url);
    return result.data;
  } catch (error) {
    console.error("Error fetching data:", error);
  }
};

export const listEntitiesForDataModel = async (
  dataModelId: string | number,
  pagination = false,
  page = 1,
  size = 10,
  check_base = true
) => {
  try {
    let url = `${apiBaseUrl}/entities/by_data_model_id/${dataModelId}?pagination=${pagination}&check_base=${check_base}`;
    if (pagination) {
      url += `&page=${page}&size=${size}`;
    }
    const result = await api.get<ApiResponse>(url);
    return result.data.data;
  } catch (error) {
    console.error("Error fetching data:", error);
  }
};

export const getModelEntityAssociations = async (modelId: number) => {
  try {
    const response = await api.get<ApiResponse>(
      `${apiBaseUrl}/entity_associations/by_data_model_id/${modelId}?pagination=false&allow_empty=true&check_base=true`
    );
    return response.data;
  } catch (error) {
    console.error("Error fetching entity associations:", error);
    throw error;
  }
};

export const getEntityAttributeAssociation = async (id: string) => {
  try {
    const result = await api.get<ApiResponse>(
      `${apiBaseUrl}/entity_attribute_associations/${id}`
    );
    return result.data;
  } catch (error) {
    console.error("Error fetching data:", error);
  }
};

export const getEntityAssociationsByParentId = async (parentId: number, modelId?: number) => {
  let url = `${apiBaseUrl}/entity_associations/by_parent_entity_id/${parentId}?pagination=false&allow_empty=true`
  url += modelId && modelId > 0 ? `&including_extended_by_data_model_id=${modelId}` : '';
  try {
    const result = await api.get<ApiResponse>(url);
    return result.data;
  } catch (error) {
    console.error("Error fetching data:", error);
  }
};


export interface EntityParams {
  Name: string;
  UniqueName: string;
  DataModelId: number;
  Description?: string;
  UseConsiderations?: string;
  Required?: boolean;
  Array?: boolean;
  Notes?: string;
  CreationDate?: string;
  ActivationDate?: string;
  DeprecationDate?: string;
  Contributor?: string;
  ContributorOrganization?: string;
  Extension?: boolean,
  Tags?: string;
}

export const createEntity = async (params: EntityParams) => {
  try {
    const response = await api.post<ApiResponse>(`${apiBaseUrl}/entities/`, params);
    return response.data;
  } catch (error) {
    console.error("Failed to create entity:", error);
    throw error;
  }
};

export const updateEntity = async (entityId: number, params: EntityParams) => {
  try {
    const response = await api.put<ApiResponse>(`${apiBaseUrl}/entities/${entityId}`, params);
    return response.data;
  } catch (error) {
    console.error("Failed to update entity:", error);
    throw error;
  }
};

export const deleteEntity = async (entityId: number) => {
  try {
    const response = await api.delete<ApiResponse>(`${apiBaseUrl}/entities/${entityId}`);
    return response.data;
  } catch (error) {
    console.error("Failed to delete entity:", error);
    throw error;
  }
};

export const deleteEntityAssociation = async (assocId: number) => {
  try {
    const response = await api.delete<ApiResponse>(`${apiBaseUrl}/entity_associations/${assocId}`);
    return response.data;
  } catch (error) {
    console.error("Failed to delete entity association:", error);
    throw error;
  }
};


export interface CreateEntityAssociationParams {
  ParentEntityId: number;
  ChildEntityId: number;
  Relationship?: string;
  Placement?: 'Embedded' | 'Reference';
  Notes?: string;
  CreationDate?: string;
  ActivationDate?: string;
  DeprecationDate?: string;
  Contributor?: string;
  ContributorOrganization?: string;
  Extension?: boolean;
  ExtensionNotes?: string;
  ExtendedByDataModelId?: number | null;
};
// Generate a template for creating an entity association
export const tmplCreateEntityAssociation = (parEntityId: number, model: any): CreateEntityAssociationParams => {
  if (!model?.Id || !model?.Type) console.warn(`templateCreateEntityAssociation has invalid model: ${model.Id}`);
  const isExt = isOverlayModel(model);
  return {
    ParentEntityId: parEntityId,
    ChildEntityId: 0,
    CreationDate: new Date().toISOString().slice(0, 16),
    ActivationDate: new Date().toISOString().slice(0, 16),
    Extension: isExt,
    ExtensionNotes: undefined,
    ExtendedByDataModelId: isExt ? model?.Id : undefined,
    Placement: 'Embedded' as CreateEntityAssociationParams["Placement"],
    Relationship: undefined,
    Contributor: undefined,
    ContributorOrganization: undefined,
  };
};

export const createEntityAssociation = async (params: CreateEntityAssociationParams) => {
  try {
    const response = await api.post<ApiResponse>(`${apiBaseUrl}/entity_associations/`, params);
    return response.data;
  } catch (error) {
    console.error("Failed to create entity association:", error);
    throw error;
  }
};

export const updateEntityAssociation = async (assocId: number, params: Partial<CreateEntityAssociationParams>) => {
  try {
    const response = await api.put<ApiResponse>(`${apiBaseUrl}/entity_associations/${assocId}`, params);
    return response.data;
  } catch (error) {
    console.error("Failed to update entity association:", error);
    throw error;
  }
};
