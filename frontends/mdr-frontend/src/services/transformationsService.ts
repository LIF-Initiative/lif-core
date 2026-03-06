import api from './api';
import { parseEntityIdPath } from '../utils/entityIdPath';

const apiBaseUrl = import.meta.env.VITE_API_URL;

export interface TransformationGroupDetails {
    Id: number;
    SourceDataModelId: number;
    SourceDataModelName?: string;
    TargetDataModelId: number;
    TargetDataModelName?: string;
    Name?: string;
    GroupVersion: string;
    Description?: string;
    Notes?: string;
    CreationDate?: string;
    ActivationDate?: string;
    DeprecationDate?: string;
    Contributor?: string;
    ContributorOrganization?: string;
    Transformations: TransformationData[];
    Tags?: string;
}

export interface TransformationData {
    Id: number;
    TransformationGroupId: number;
    Name: string;
    Expression: string;
    ExpressionLanguage: string;
    Notes: string;
    Alignment: string;
    CreationDate: string;
    ActivationDate: string;
    DeprecationDate: string;
    Contributor: string;
    ContributorOrganization: string;
    // Backend now returns multi-source only (legacy SourceAttribute removed)
    SourceAttributes?: Array<{
        AttributeId: number;
        AttributeType?: string;
        EntityIdPath?: string; // format: comma-separated IDs, e.g. "654,22,6,-352" (negative = attribute)
        Notes?: string;
        CreationDate?: string;
        ActivationDate?: string;
        DeprecationDate?: string;
        Contributor?: string;
        ContributorOrganization?: string;
    }>;
    TargetAttribute: {
        AttributeId: number;
        EntityId: number;
        AttributeName: string;
        AttributeType: string;
        EntityIdPath?: string;
        Notes: string;
        CreationDate: string;
        ActivationDate: string;
        DeprecationDate: string;
        Contributor: string;
        ContributorOrganization: string;
    };
}

export interface CreateTransformationAttribute {
    AttributeId: number;
    AttributeType: string;
    EntityId?: number; // required by backend validation
    EntityIdPath?: string; // API format: comma-separated IDs, e.g. "654,22,6,-352" (negative = attribute)
    Notes?: string;
    CreationDate?: string;
    ActivationDate?: string;
    DeprecationDate?: string;
    Contributor?: string;
    ContributorOrganization?: string;
}

export interface CreateTransformation {
    TransformationGroupId: number;
    Name?: string;
    Expression: string;
    ExpressionLanguage?: 'JSONata' | 'Python' | 'Perl' | 'LIF_Pseudo_Code' | 'SQL';
    Notes?: string;
    Alignment?: string;
    CreationDate?: string;
    ActivationDate?: string;
    DeprecationDate?: string;
    Contributor?: string;
    ContributorOrganization?: string;
    // Attributes optional on create; legacy single SourceAttribute removed
    SourceAttributes?: CreateTransformationAttribute[]; // multi-source
    TargetAttribute?: CreateTransformationAttribute;
}

export interface PaginatedResponse<T> {
    data: T[];
    total: number;
    page?: number;
    size?: number;
    total_pages?: number;
    next?: string;
    previous?: string;
}

export interface TransformationGroupPaginatedResponse {
    data: TransformationGroupDetails;
    total: number;
    page?: number;
    size?: number;
    total_pages?: number;
    next?: string;
    previous?: string;
}

export interface TranformationGroupData {
    TransformationGroupId: number;
    SourceDataModelId: number;
    SourceDataModelName: string;
    TargetDataModelId: number;
    TargetDataModelName: string;
}

export interface CreateTransformationGroup {
    SourceDataModelId: number;
    TargetDataModelId: number;
    Name?: string;
    GroupVersion: string; // for some reason this is required... 1.0 etc
    Description?: string;
    Notes?: string;
    CreationDate?: string;
    ActivationDate?: string;
    DeprecationDate?: string;
    Contributor?: string;
    ContributorOrganization?: string;
    Transformations?: any[];
}

export const existsTransformationGroup = async (
    sourceId: number,
    targetId: number,
    version: string,
    includeDeleted = true
) => {
    const url = `${apiBaseUrl}/transformation_groups/exists/by-triplet?sourceId=${sourceId}&targetId=${targetId}&version=${encodeURIComponent(
        version
    )}&include_deleted=${includeDeleted ? 'true' : 'false'}`;
    const result = await api.get(url);
    return result.data as { exists: boolean; id?: number; deleted?: boolean };
};

export const listAllTransformationGroups = async () => {
    const result = await api.get<TranformationGroupData[]>(
        `${apiBaseUrl}/transformation_groups/data_models/`
    );
    return result.data;
};

export const getTransformationsForGroup = async (
    id: number,
    pagination = false,
    page = 1,
    size = 10
) => {
    let url = `${apiBaseUrl}/transformation_groups/${id}?pagination=${pagination}`;
    let result = null;
    if (pagination) {
        url += `&page=${page}&size=${size}`;
    }
    result = await api.get<TransformationGroupPaginatedResponse>(url);
    return result?.data;
};

// New endpoints introduced by backend
export const getGroupBySourceAndTarget = async (
    sourceDataModelId: number,
    targetDataModelId: number
) => {
    const url = `${apiBaseUrl}/transformation_groups/source_and_target/?source_data_model_id=${sourceDataModelId}&target_data_model_id=${targetDataModelId}`;
    const res = await api.get(url);
    return res.data as TransformationGroupDetails | null;
};

export const getTransformationsForDataModels = async (
    sourceDataModelId: number,
    targetDataModelId: number
) => {
    const url = `${apiBaseUrl}/transformations_for_data_models/?source_data_model_id=${sourceDataModelId}&target_data_model_id=${targetDataModelId}`;
    const res = await api.get(url);
    return res.data as TransformationData[];
};

export const getTransformationsByPathIds = async (
    entityIdPath: string,
    attributeId: number
) => {
    const url = `${apiBaseUrl}/transformations_by_path_ids/?entity_id_path=${encodeURIComponent(
        entityIdPath
    )}&attribute_id=${attributeId}`;
    const res = await api.get(url);
    return res.data as TransformationData[];
};

export const getTransformationGroupData = async (id: number) => {
    const allGroups = await listAllTransformationGroups();
    return allGroups.find((group) => group.TransformationGroupId === id);
};

// TODO: transformation group tags CRUD

export const createTransformationGroup = async (
    createParameters: CreateTransformationGroup,
    transformations?: any[]
) => {
    const url = `${apiBaseUrl}/transformation_groups/`;

    const postParameters = {
        ...createParameters,
    };
    if (transformations?.length) {
        postParameters.Transformations = transformations;
    }

    const result = await api.post(url, postParameters);
    return result.data;
};

export const updateTransformationGroup = async (
    id: number,
    updates: Partial<CreateTransformationGroup>
) => {
    const url = `${apiBaseUrl}/transformation_groups/${id}`;
    const result = await api.put(url, updates);
    return result.data;
};

export const deleteTransformationGroup = async (id: number) => {
    const url = `${apiBaseUrl}/transformation_groups/${id}`;
    const res = await api.delete(url);
    return res.data as { success: boolean };
};

export const updateTransformationExpression = async (
    id: number,
    expression: string,
    transformationGroupId?: number
) => {
    const url = `${apiBaseUrl}/transformation_groups/transformations/${id}`;
    const body: any = { Expression: expression };
    // Backend requires TransformationGroupId for validation; include if provided
    if (typeof transformationGroupId === 'number') {
        body.TransformationGroupId = transformationGroupId;
    }
    const result = await api.put(url, body);
    return result.data;
};

export const createTransformation = async (
    transformation: CreateTransformation
) => {
    const url = `${apiBaseUrl}/transformation_groups/transformations/`;
    // Per backend notes: only TransformationGroupId and Expression are required; default ExpressionLanguage to JSONata
    const payload = {
        ExpressionLanguage: 'JSONata',
        ...transformation,
    };
    const result = await api.post(url, payload);
    return result.data;
};

/**
 * Creates a new transformation or updates an existing one if a transformation
 * with the same target attribute already exists in the group.
 * When updating, the new source attributes are appended to the existing SourceAttributes array.
 * @param transformation - The transformation to create or merge
 * @param existingTransformations - Optional array of existing transformations to check against.
 *                                   If not provided, will fetch from the group.
 * @returns The created or updated transformation data
 */
export const createOrUpdateTransformation = async (
    transformation: CreateTransformation,
    existingTransformations?: TransformationData[]
): Promise<TransformationData> => {
    const { TransformationGroupId, TargetAttribute, SourceAttributes } = transformation;
    
    // If no target attribute specified, just create a new transformation
    if (!TargetAttribute?.AttributeId) {
        return await createTransformation(transformation);
    }

    // Get existing transformations if not provided
    let transformations = existingTransformations;
    if (!transformations) {
        const groupData = await getTransformationsForGroup(TransformationGroupId, false);
        transformations = groupData?.data?.Transformations || [];
    }

    // Find existing transformation with the same target attribute
    const existingTransformation = transformations.find((t) => {
        const tgtAttr = t.TargetAttribute;
        if (!tgtAttr) return false;
        
        // Match by AttributeId and EntityIdPath (if present)
        const matchesAttributeId = tgtAttr.AttributeId === TargetAttribute.AttributeId;
        const matchesEntityIdPath = 
            (!TargetAttribute.EntityIdPath && !tgtAttr.EntityIdPath) ||
            tgtAttr.EntityIdPath === TargetAttribute.EntityIdPath;
        
        return matchesAttributeId && matchesEntityIdPath;
    });

    if (existingTransformation) {
        // Merge source attributes - append new ones to existing
        const existingSourceAttrs = existingTransformation.SourceAttributes || [];
        const newSourceAttrs = SourceAttributes || [];
        
        // Filter out duplicates based on AttributeId and EntityIdPath
        const mergedSourceAttrs = [...existingSourceAttrs];
        for (const newAttr of newSourceAttrs) {
            const isDuplicate = existingSourceAttrs.some(
                (existing) =>
                    existing.AttributeId === newAttr.AttributeId &&
                    existing.EntityIdPath === newAttr.EntityIdPath
            );
            if (!isDuplicate) {
                mergedSourceAttrs.push(newAttr as any);
            }
        }

        // Build target attribute payload from existing transformation to ensure v2 validation
        // is triggered on the backend (it checks TargetAttribute.EntityIdPath for format detection)
        const existingTarget = existingTransformation.TargetAttribute;
        const targetAttrPayload: CreateTransformationAttribute | undefined = existingTarget
            ? {
                  AttributeId: existingTarget.AttributeId,
                  AttributeType: existingTarget.AttributeType || 'Target',
                  EntityId: existingTarget.EntityId,
                  EntityIdPath: existingTarget.EntityIdPath,
              }
            : TargetAttribute;

        // Update the existing transformation with merged source attributes
        // Pass TargetAttribute so backend uses v2 EntityIdPath validation
        const updated = await updateTransformationAttributes(
            existingTransformation.Id,
            { 
                SourceAttributes: mergedSourceAttrs as CreateTransformationAttribute[],
                TargetAttribute: targetAttrPayload,
            },
            TransformationGroupId
        );
        
        return updated as TransformationData;
    }

    // No existing transformation found, create a new one
    return await createTransformation(transformation);
};

export const updateTransformation = async (
    id: number,
    updates: Partial<TransformationData>
) => {
    const url = `${apiBaseUrl}/transformation_groups/transformations/${id}`;

    // Omit Id (path param supplies it) but KEEP TransformationGroupId as backend validator needs it
    const { Id, ...rest } = updates as any;
    const result = await api.put(url, rest);
    return result.data;
};

// Optional helper to update only attributes (multi-source supported)
export const updateTransformationAttributes = async (
    id: number,
    params: {
        SourceAttributes?: CreateTransformationAttribute[];
        TargetAttribute?: CreateTransformationAttribute;
    },
    transformationGroupId?: number
) => {
    const url = `${apiBaseUrl}/transformation_groups/transformations/${id}`;
    const body = transformationGroupId
        ? { TransformationGroupId: transformationGroupId, ...params }
        : params as any;
    const result = await api.put(url, body);
    return result.data;
};

export const deleteTransformation = async (id: number) => {
    const url = `${apiBaseUrl}/transformation_groups/transformations/${id}`;
    const result = await api.delete(url);
    return result.data;
};

// ---------------- Value Mappings ----------------
export interface ValueMapping {
    Id: number;
    TransformationGroupId: number;
    SourceValueSetId: number;
    SourceValueId: number;
    TargetValueSetId: number;
    TargetValueId: number;
    Notes?: string;
    CreationDate?: string;
    ActivationDate?: string;
    DeprecationDate?: string;
}

export type CreateValueMapping = Omit<
    ValueMapping,
    'Id' | 'CreationDate' | 'ActivationDate' | 'DeprecationDate'
>;

export const createValueMapping = async (payload: CreateValueMapping) => {
    const url = `${apiBaseUrl}/value_mappings/`;
    const res = await api.post(url, payload);
    return res.data as ValueMapping;
};

export const getValueMapping = async (id: number) => {
    const url = `${apiBaseUrl}/value_mappings/${id}`;
    const res = await api.get(url);
    return res.data as ValueMapping;
};

export const getValueMappingsByTransformationGroup = async (
    transformationGroupId: number
) => {
    // Try namespaced route first, then fallback to top-level as per backend notes
    try {
        const url1 = `${apiBaseUrl}/value_mappings/by_transformation_group/${transformationGroupId}`;
        const res1 = await api.get(url1);
        return res1.data as ValueMapping[];
    } catch {
        const url2 = `${apiBaseUrl}/by_transformation_group/${transformationGroupId}`;
        const res2 = await api.get(url2);
        return res2.data as ValueMapping[];
    }
};

export const getValueMappingsByValueIds = async (
    sourceValueId?: number,
    targetValueId?: number
) => {
    const params: string[] = [];
    if (typeof sourceValueId === 'number') params.push(`source_value_id=${sourceValueId}`);
    if (typeof targetValueId === 'number') params.push(`target_value_id=${targetValueId}`);
    try {
        const url1 = `${apiBaseUrl}/value_mappings/by_value_ids/?${params.join('&')}`;
        const res1 = await api.get(url1);
        return res1.data as ValueMapping[];
    } catch {
        const url2 = `${apiBaseUrl}/by_value_ids/?${params.join('&')}`;
        const res2 = await api.get(url2);
        return res2.data as ValueMapping[];
    }
};

export const getValueMappingsByValueSetIds = async (
    sourceValueSetId?: number,
    targetValueSetId?: number
) => {
    const params: string[] = [];
    if (typeof sourceValueSetId === 'number') params.push(`source_value_set_id=${sourceValueSetId}`);
    if (typeof targetValueSetId === 'number') params.push(`target_value_set_id=${targetValueSetId}`);
    try {
        const url1 = `${apiBaseUrl}/value_mappings/by_value_ids/?${params.join('&')}`;
        const res1 = await api.get(url1);
        return res1.data as ValueMapping[];
    } catch {
        const url2 = `${apiBaseUrl}/by_value_ids/?${params.join('&')}`;
        const res2 = await api.get(url2);
        return res2.data as ValueMapping[];
    }
};

export const updateValueMapping = async (
    id: number,
    updates: Partial<CreateValueMapping>
) => {
    const url = `${apiBaseUrl}/value_mappings/${id}`;
    const res = await api.put(url, updates);
    return res.data as ValueMapping;
};

export const deleteValueMapping = async (id: number) => {
    const url = `${apiBaseUrl}/value_mappings/${id}`;
    const res = await api.delete(url);
    return res.data as { success: boolean };
};

export type VersionBump = 'major' | 'minor';

// Internal helpers shared across functions
const parseVersionParts = (v?: string): { major: number; minor: number } => {
    if (!v) return { major: 1, minor: 0 };
    const m = String(v).match(/(\d+)\.(\d+)/);
    if (!m) return { major: 1, minor: 0 };
    return { major: parseInt(m[1], 10) || 1, minor: parseInt(m[2], 10) || 0 };
};
const fmtVersion = (p: { major: number; minor: number }) =>
    `${p.major}.${p.minor}`;

/**
 * Compute the next version string for a group given a bump type by scanning
 * all other groups with the same source/target pair.
 */
export const computeNextVersion = async (
    groupId: number,
    bump: VersionBump
): Promise<string> => {
    const currResp = await getTransformationsForGroup(groupId, false);
    if (!currResp) return bump === 'major' ? '2.0' : '1.1';
    const curr = currResp.data;
    const currentParts = parseVersionParts(curr.GroupVersion);
    const all = await listAllTransformationGroups();
    const normalizeId = (id?: number) => (id && id > 0 ? id : 1);
    const samePair = (all || []).filter(
        (g) =>
            g.SourceDataModelId === curr.SourceDataModelId &&
            normalizeId(g.TargetDataModelId) === normalizeId(curr.TargetDataModelId)
    );
    // Fetch versions for samePair ids
    const vers = await Promise.all(
        samePair.map(async (g) => {
            try {
                const r = await getTransformationsForGroup(
                    g.TransformationGroupId,
                    false
                );
                return parseVersionParts(r?.data.GroupVersion);
            } catch {
                return null;
            }
        })
    );
    const parts = vers.filter(Boolean) as Array<{
        major: number;
        minor: number;
    }>;
    let proposal: { major: number; minor: number };
    if (bump === 'major') {
        const maxMajor = parts.reduce(
            (m, p) => Math.max(m, p.major),
            currentParts.major
        );
        proposal = { major: maxMajor + 1, minor: 0 };
    } else {
        const maxMinorForMajor = parts
            .filter((p) => p.major === currentParts.major)
            .reduce((m, p) => Math.max(m, p.minor), currentParts.minor);
        proposal = { major: currentParts.major, minor: maxMinorForMajor + 1 };
    }

    // Ensure proposed version doesn't collide with existing (including deleted) groups
    const existsFor = async (ver: { major: number; minor: number }) => {
        const version = fmtVersion(ver);
        const ok = await existsTransformationGroup(
            curr.SourceDataModelId,
            normalizeId(curr.TargetDataModelId),
            version,
            true
        );
        return ok?.exists;
    };
    // If collision, bump minor until free
    while (await existsFor(proposal)) {
        proposal = { major: proposal.major, minor: proposal.minor + 1 };
    }
    return fmtVersion(proposal);
};

/**
 * Forks an existing transformation group into a new group with an incremented version.
 * - Copies group metadata (except dates) and all transformations.
 * - Sets CreationDate to now; ActivationDate/DeprecationDate cleared.
 * - If source GroupVersion is missing, defaults to 1.0.
 * - bump: 'major' increments the major part and resets minor to 0; 'minor' increments minor.
 */
export const forkTransformationGroup = async (
    groupOrId: TransformationGroupDetails | number,
    bump: VersionBump = 'major'
): Promise<TransformationGroupDetails> => {
    const original =
        typeof groupOrId === 'number'
            ? (await getTransformationsForGroup(groupOrId, false))!.data
            : groupOrId;
    // Determine next version using global knowledge of same Source/Target pair
    const nextVersion = await computeNextVersion(original.Id, bump);

    const nowIso = new Date().toISOString();
    const normalize = (id?: number) => (id && id > 0 ? id : 1);

    // Create the new group (without transformations first)
    const newGroup = await createTransformationGroup({
        SourceDataModelId: original.SourceDataModelId,
        TargetDataModelId: normalize(original.TargetDataModelId),
        Name: original.Name,
        GroupVersion: nextVersion,
        Description: original.Description,
        Notes: original.Notes,
        CreationDate: nowIso,
        ActivationDate: undefined,
        DeprecationDate: undefined,
        Contributor: original.Contributor,
        ContributorOrganization: original.ContributorOrganization,
    });

    // Clone transformations to the new group
    const createdTransforms: TransformationData[] = [];
    for (const t of original.Transformations || []) {
        try {
            const srcList: CreateTransformationAttribute[] = [];
            if (Array.isArray((t as any).SourceAttributes)) {
                for (const s of (t as any).SourceAttributes) {
                    if (s?.AttributeId) {
                        srcList.push({
                            AttributeId: s.AttributeId,
                            AttributeType: s.AttributeType || 'Source',
                            EntityIdPath: (s as any).EntityIdPath,
                            EntityId: (s as any)?.EntityId || (() => {
                                // Derive EntityId from EntityIdPath (supports both old dot and new comma format)
                                const parsed = parseEntityIdPath((s as any)?.EntityIdPath);
                                if (parsed && parsed.entityIds.length > 0) {
                                    return parsed.entityIds[parsed.entityIds.length - 1];
                                }
                                return undefined;
                            })(),
                        });
                    }
                }
            }
            let tgtPayload: CreateTransformationAttribute | undefined;
            if ((t as any).TargetAttribute?.AttributeId) {
                const g = (t as any).TargetAttribute;
                tgtPayload = {
                    AttributeId: g.AttributeId,
                    AttributeType: g.AttributeType || 'Target',
                    EntityIdPath: (g as any).EntityIdPath,
                    EntityId: (g as any)?.EntityId || (() => {
                        // Derive EntityId from EntityIdPath (supports both old dot and new comma format)
                        const parsed = parseEntityIdPath((g as any)?.EntityIdPath);
                        if (parsed && parsed.entityIds.length > 0) {
                            return parsed.entityIds[parsed.entityIds.length - 1];
                        }
                        return undefined;
                    })(),
                };
            }
            const created = await createTransformation({
                TransformationGroupId: newGroup.Id,
                Name: t.Name,
                Expression: t.Expression ?? '$',
                ExpressionLanguage: 'JSONata',
                Notes: t.Notes,
                Alignment: t.Alignment,
                SourceAttributes: srcList.length ? srcList : undefined,
                TargetAttribute: tgtPayload,
            });

            createdTransforms.push(created as TransformationData);
        } catch (e) {
            // Log and continue cloning others
            console.error('Failed to clone transformation', t?.Id, e);
        }
    }

    // Return merged new group details
    const merged: TransformationGroupDetails = {
        ...newGroup,
        GroupVersion: newGroup.GroupVersion || nextVersion,
        Transformations: createdTransforms,
    } as TransformationGroupDetails;
    return merged;
};
