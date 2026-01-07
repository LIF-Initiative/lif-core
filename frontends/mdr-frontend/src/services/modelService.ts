import { faker } from '@faker-js/faker';
import {
  ApiResponse,
  CountResponse,
  DataModel,
  DataModelWithDetailsDTO,
  DataModelWithDetailsWithTree,
  EntityTreeNode,
  EntityWithAttributesDTO,
  StateType,
} from "../types";
import api from "./api";

const apiBaseUrl = import.meta.env.VITE_API_URL;

/**
 * List data models, optionally filtering by DataModel.Type on the client side.
 * Example types could include "SourceSchema", "Base", "Extension", etc.
 */
export const listModels = async (
  filters?: { type?: string | string[] }
): Promise<DataModel[]> => {
  try {
    const result = await api.get<ApiResponse>(
      `${apiBaseUrl}/datamodels/?pagination=false`);
    let models = result.data.data;

    // Optional client-side type filter
    if (filters?.type) {
      const toArray = Array.isArray(filters.type)
        ? filters.type
        : [filters.type];
      const wanted = new Set(
        toArray
          .filter((t) => t != null)
          .map((t) => String(t).trim().toLowerCase())
      );
      models = models.filter(
        (m) => m.Type && wanted.has(String(m.Type).trim().toLowerCase())
      );
    }

    return models;
  } catch (error) {
    console.error("Error fetching data:", error);
    throw error;
  }
};

export const getModel = async (id: number) => {
  try {
    const result = await api.get<ApiResponse>(`${apiBaseUrl}/datamodels/${id}`);
    return result.data;
  } catch (error) {
    console.error("Error fetching data:", error);
    throw error;
  }
};

export const getModelDetails = async (id: number, params?: string): Promise<DataModelWithDetailsDTO> => {
  try {
    const basePath = `${apiBaseUrl}/datamodels/with_details/${id}`;
    const queryPath = basePath + (params ? `?${params}` : "");
    // console.log("getModelDetails queryPath:", queryPath);
    const result = await api.get<DataModelWithDetailsDTO>(queryPath);
    return result.data;
  } catch (error) {
    console.error("Error fetching data:", error);
    throw error;
  }
};

/**
 * Fetches model details and augments them with an EntityTree derived from
 * ParentEntities/ChildEntities relationships.
 *
 * Rules applied:
 * - If a child relationship is not null and does not start with "has" or "relevant",
 *   the child's display name is prefixed with the relationship (e.g., "owns Asset").
 * - If ChildEntityDTO.Placement === "Reference" (case-insensitive), treat it as a reference:
 *   only the required attributes of that child entity are included, and no child entities are shown.
 *
 * Note: Nodes generally reference the existing entity objects from the response,
 * but for Reference placements and/or relationship-prefixed labels a shallow clone
 * is used to adjust display Name and/or filter Attributes for that node only.
 */
export const getModelDetailsWithTree = async (
  id: number,
  params?: string
): Promise<DataModelWithDetailsWithTree> => {
  const details = await getModelDetails(id, params);

  // Build quick lookups for entity by id and its children ids
  const entityById = new Map<number, EntityWithAttributesDTO>();
  details.Entities.forEach((ewa) => entityById.set(ewa.Entity.Id, ewa));

  // Track placements for each entity when it appears as a child so we can identify
  // entities that are ONLY ever referenced (Placement === 'Reference'). Those will
  // also be promoted to root-level entities per new rule.
  const childPlacements = new Map<number, Set<string>>();
  details.Entities.forEach((ewa) => {
    (ewa.ChildEntities || []).forEach((c: any) => {
      const set = childPlacements.get(c.Id) || new Set<string>();
      if (c.Placement != null) set.add(String(c.Placement).trim().toLowerCase());
      else set.add("__null"); // mark null/undefined distinctly so it disqualifies reference-only status
      childPlacements.set(c.Id, set);
    });
  });

  const hasParent = new Set<number>();
  details.Entities.forEach((ewa) => {
    ewa.ParentEntities.forEach((p) => hasParent.add(ewa.Entity.Id));
  });

  const referenceOnlyEntityIds = new Set<number>();
  childPlacements.forEach((placements, childId) => {
    if (placements.size === 0) return;
    // Entity is reference-only if every placement collected is exactly 'reference'.
    // Any null/blank/embedded/other value disqualifies.
    const allReference = Array.from(placements).every((pl) => pl === 'reference');
    if (allReference) referenceOnlyEntityIds.add(childId);
  });

  // Roots are entities with no parents
  // New rule: also treat entities that only ever appear as Reference children as additional roots
  const roots = details.Entities.filter((ewa) => !hasParent.has(ewa.Entity.Id) || referenceOnlyEntityIds.has(ewa.Entity.Id));

  const normalize = (s: string | null | undefined) => (s ?? '').trim();
  const isReferencePlacement = (p?: string | null) => normalize(p).toLowerCase() === 'reference';
  const shouldPrefixRelationship = (rel?: string | null) => {
    const r = normalize(rel);
    if (!r) return false;
    const lower = r.toLowerCase();
    return !(lower.startsWith('has') || lower.startsWith('relevant'));
  };
  const prefixRelationshipName = (name: string, rel?: string | null) =>
    shouldPrefixRelationship(rel) ? `${normalize(rel)}Ref${name}` : name;

  const isRequiredAttribute = (required: string | null | undefined) => {
    const r = normalize(required).toLowerCase();
    if (!r) return false;
    return r === 'yes' || r === 'y' || r === 'true' || r === 'required' || r === 'mandatory';
  };

  const filterRequiredAttributes = (attrs: EntityWithAttributesDTO['Attributes']) =>
    (attrs || []).filter((a) => isRequiredAttribute(a.Required));

  const makeNode = (
    ewa: EntityWithAttributesDTO,
    pathEntityIds: string,
    namePrefix: string,
    siblingIndex: number,
    visitedIds: Set<number>
  ): EntityTreeNode => {
    // PathId should be the entity ID chain (e.g., "4.238") to align with backend EntityIdPath
    const eid = String(ewa.Entity.Id);
    const pathId = pathEntityIds ? `${pathEntityIds}.${eid}` : eid;
    const pathName = namePrefix ? `${namePrefix}.${ewa.Entity.Name}` : ewa.Entity.Name;

    // Avoid infinite loops in case of accidental cycles
    const nextVisited = new Set(visitedIds);
    nextVisited.add(ewa.Entity.Id);

    const children: EntityTreeNode[] = [];
    ewa.ChildEntities.forEach((childEntityDTO, idx) => {
      const child = entityById.get(childEntityDTO.Id);
      if (!child) return;
      if (nextVisited.has(child.Entity.Id)) return; // guard against cycles

      const isRef = isReferencePlacement(childEntityDTO.Placement);
      const displayName = prefixRelationshipName(child.Entity.Name, childEntityDTO.Relationship);

      // Shallow clone the child EWA to adjust display name and/or attributes for this node only
      const adjustedChild: EntityWithAttributesDTO = {
        ...child,
        Entity: child.Entity.Name === displayName ? child.Entity : { ...child.Entity, Name: displayName },
        Attributes: isRef ? filterRequiredAttributes(child.Attributes) : child.Attributes,
        // For references, display no child entities
        ChildEntities: isRef ? [] : child.ChildEntities,
      };

      if (isRef) {
        const childPathId = `${pathId}.${child.Entity.Id}`;
        const childPathName = `${pathName}.${displayName}`;
        children.push({
          PathId: childPathId,
          PathName: childPathName,
          EntityId: child.Entity.Id,
          Entity: adjustedChild,
          Children: [],
        });
        return;
      }

      children.push(makeNode(adjustedChild, pathId, pathName, idx + 1, nextVisited));
    });

    return {
      PathId: pathId,
      PathName: pathName,
      EntityId: ewa.Entity.Id,
      Entity: ewa, // keep reference to the same object
      Children: children,
    };
  };

  const tree: EntityTreeNode[] = roots.map((ewa, idx) =>
    makeNode(ewa, "", "", idx + 1, new Set())
  );

  // console.log("Entity tree:", tree, "Reference-only promoted roots:", Array.from(referenceOnlyEntityIds));
  return Object.assign({}, details, { EntityTree: tree });
};

/**
 * Generate a single hierarchical sample JSON object from a model's EntityTree.
 * Top-level keys are root entity names. Each entity can either be:
 *  - An object of its attributes (and nested entities)
 *  - An array of such objects if Entity.Array === 'Yes' (case-insensitive) OR null (null defaults to Yes).
 *
 * Parameter 'count' controls ONLY the number of objects created for root-level array entities.
 * Nested array entities ALWAYS get exactly 1 object element (still wrapped in an array to reflect schema).
 *
 * Attribute value generation rules (unchanged from prior implementation):
 *  - Use Attribute.Example if present (non-empty).
 *  - Otherwise infer based on DataType (string/number/boolean/date/enum); unknown -> string.
 *  - Enum picks a random ValueName/Value from its ValueSet (if available).
 *
 * Repeated root entity names are disambiguated by suffix _N.
 */
export function generateSampleRecords(
  model: DataModelWithDetailsWithTree | DataModelWithDetailsDTO,
  tree: EntityTreeNode[],
  count: number
): any {
  const rootArrayCount = Math.max(0, Math.min(count, 100));

  // Value set lookup for enum support
  const valueSetMap = new Map<number, { names: string[] }>();
  const valueSets = (model as any).ValueSets || [];
  valueSets.forEach((vs: any) => {
    const names = Array.isArray(vs.Values)
      ? vs.Values.map((v: any) => v?.ValueName || v?.Value).filter((v: any) => v != null)
      : [];
    valueSetMap.set(vs.ValueSet?.Id || vs.ValueSetId || vs.Id, { names });
  });

  const lc = (s: any) => String(s || "").toLowerCase();

  const genValue = (attr: any) => {
    const example = attr?.Example;
    if (example !== null && example !== undefined && example !== "") return example;
    const isArray = attr?.Array && attr.Array !== "No";
    const dt = lc(attr?.DataType || "string");
    let myGenVal: any = "";
    switch (dt) {
      case "number":
      case "int":
      case "integer":
        myGenVal = faker.number.int({ min: 0, max: 1000 });
        break;
      case "float":
      case "double":
        myGenVal = faker.number.float({ min: 0, max: 1000, fractionDigits: 2 });
        break;
      case "boolean":
      case "bool":
        myGenVal = faker.datatype.boolean();
        break;
      case "date":
      case "datetime":
      case "timestamp":
        myGenVal = faker.date.recent({ days: 30 }).toISOString();
        break;
      case "enum": {
        const vsId = attr?.ValueSetId;
        if (vsId && valueSetMap.has(vsId)) {
          const { names } = valueSetMap.get(vsId)!;
          if (names.length) {
            myGenVal = names[Math.floor(Math.random() * names.length)];
            break;
          }
        }
        myGenVal = faker.helpers.arrayElement([
          faker.word.sample(),
          faker.word.noun(),
          faker.word.adjective(),
        ]);
        break;
      }
      case "string":
      default: {
        const nameLc = lc(attr?.Name);
        if (nameLc.includes("id")) myGenVal = faker.string.uuid();
        if (nameLc.includes("email")) myGenVal = faker.internet.email();
        if (nameLc.includes("name")) myGenVal = faker.person.fullName();
        if (nameLc.includes("date")) myGenVal = faker.date.recent().toISOString();
        if (nameLc.includes("url")) myGenVal = faker.internet.url();
        myGenVal = myGenVal || faker.lorem.word();
      }
    }
    return isArray ? [myGenVal] : myGenVal;
  };

  const isArrayEntity = (wrapper: any) => {
    const meta = wrapper?.Entity?.Id ? wrapper.Entity : wrapper;
    const arr = meta?.Array; // 'Yes' | 'No' | null
    if (arr == null) return true; // default to Yes
    return String(arr).trim().toLowerCase() === 'yes';
  };

  const buildEntityContent = (node: EntityTreeNode): any => {
    const entityWrapper: any = node.Entity as any;
    const attrs = (entityWrapper.Attributes || []) as any[];
    const obj: any = {};
    attrs.forEach((attr) => {
      const key = attr.Name || attr.UniqueName || `attr_${attr.Id}`;
      obj[key] = genValue(attr);
    });
    if (node.Children && node.Children.length) {
      node.Children.forEach((child) => {
        const childWrapper: any = child.Entity as any;
        const childMeta = childWrapper.Entity?.Id ? childWrapper.Entity : childWrapper;
        const childName = childMeta.Name || childMeta.UniqueName || `Entity_${child.EntityId}`;
        const childIsArray = isArrayEntity(childWrapper);
        const childValue = buildEntityObject(child, false); // returns object or array
        obj[childName] = childValue;
        if (childIsArray && Array.isArray(childValue) && childValue.length === 0) {
          // ensure at least one element for nested arrays
          childValue.push(buildEntityContent(child));
        }
      });
    }
    return obj;
  };

  const buildEntityObject = (node: EntityTreeNode, isRoot: boolean): any => {
    const wrapper: any = node.Entity as any;
    const arrayFlag = isArrayEntity(wrapper);
    if (!arrayFlag) {
      return buildEntityContent(node);
    }
    // Array case
    const desired = isRoot ? rootArrayCount : 1; // nested arrays -> single element
    const arr: any[] = [];
    for (let i = 0; i < desired; i++) {
      arr.push(buildEntityContent(node));
    }
    return arr;
  };

  const rootNamesCounter = new Map<string, number>();
  const rootObject: any = {};
  tree.forEach((rootNode) => {
    const rootWrapper: any = rootNode.Entity as any;
    const meta = rootWrapper.Entity?.Id ? rootWrapper.Entity : rootWrapper;
    let rootName = meta.Name || meta.UniqueName || `Entity_${rootNode.EntityId}`;
    if (rootObject[rootName] !== undefined) {
      const idx = (rootNamesCounter.get(rootName) || 0) + 1;
      rootNamesCounter.set(rootName, idx);
      rootName = `${rootName}_${idx}`;
    } else {
      rootNamesCounter.set(rootName, 0);
    }
    rootObject[rootName] = buildEntityObject(rootNode, true);
  });

  return rootObject;
}

/**
 * Generate a JSON Schema (draft 2020-12) from the provided EntityTree.
 *
 * Rules / Mapping:
 *  - Each root entity becomes a top-level property on the returned schema's root object.
 *  - If an entity's Array flag (Entity.Array) is 'Yes' (or null -> default Yes) it is represented as
 *    { type: 'array', items: <entityObjectSchema> }. Otherwise just the object schema.
 *  - Attributes map to JSON Schema primitive types based on DataType (string/number/integer/boolean/date/datetime/timestamp/enum).
 *  - Enum attributes include an 'enum' keyword populated from associated ValueSet values (when available).
 *  - Required attributes are gathered using the same heuristics as elsewhere (Required in ['yes','y','true','required','mandatory']).
 *  - Child entities become nested properties (recursively applying the same array logic).
 *  - Duplicate root entity names get suffixed ( _N ) just like sample record generation to avoid collisions.
 *  - additionalProperties is set to false for generated object schemas to keep them strict (can be relaxed if needed).
 */
export function generateJsonSchema(
  model: DataModelWithDetailsWithTree | DataModelWithDetailsDTO,
  tree: EntityTreeNode[]
): any {
  const lc = (s: any) => String(s || '').toLowerCase();

  // Build value set map for enum expansion
  const valueSetMap = new Map<number, { names: string[] }>();
  const valueSets = (model as any).ValueSets || [];
  valueSets.forEach((vs: any) => {
    const names = Array.isArray(vs.Values)
      ? vs.Values.map((v: any) => v?.ValueName || v?.Value).filter((v: any) => v != null)
      : [];
    valueSetMap.set(vs.ValueSet?.Id || vs.ValueSetId || vs.Id, { names });
  });

  const isArrayEntity = (wrapper: any) => {
    const meta = wrapper?.Entity?.Id ? wrapper.Entity : wrapper;
    const arr = meta?.Array; // 'Yes' | 'No' | null
    if (arr == null) return true; // default to Yes
    return String(arr).trim().toLowerCase() === 'yes';
  };

  const isRequiredAttribute = (required: string | null | undefined) => {
    const r = lc(required).trim();
    if (!r) return false;
    return (
      r === 'yes' ||
      r === 'y' ||
      r === 'true' ||
      r === 'required' ||
      r === 'mandatory'
    );
  };

  const mapAttribute = (attr: any) => {
    const dt = lc(attr?.DataType || 'string');
    switch (dt) {
      case 'number':
      case 'int':
      case 'integer':
        return { type: 'integer' };
      case 'float':
      case 'double':
        return { type: 'number' };
      case 'boolean':
      case 'bool':
        return { type: 'boolean' };
      case 'date':
      case 'datetime':
      case 'timestamp':
        return { type: 'string', format: 'date-time' };
      case 'enum': {
        const vsId = attr?.ValueSetId;
        if (vsId && valueSetMap.has(vsId)) {
          const { names } = valueSetMap.get(vsId)!;
          if (names.length) {
            return { type: 'string', enum: names };
          }
        }
        return { type: 'string' };
      }
      case 'string':
      default:
        return { type: 'string' };
    }
  };

  const buildEntitySchema = (node: EntityTreeNode): any => {
    const wrapper: any = node.Entity as any;
    const attrs = (wrapper.Attributes || []) as any[];
    const properties: Record<string, any> = {};
    const required: string[] = [];
    attrs.forEach(attr => {
      const key = attr.Name || attr.UniqueName || `attr_${attr.Id}`;
      properties[key] = mapAttribute(attr);
      if (isRequiredAttribute(attr.Required)) required.push(key);
    });
    if (node.Children && node.Children.length) {
      node.Children.forEach(child => {
        const childWrapper: any = child.Entity as any;
        const meta = childWrapper.Entity?.Id ? childWrapper.Entity : childWrapper;
        const childName = meta.Name || meta.UniqueName || `Entity_${child.EntityId}`;
        const childSchema = buildNode(child);
        properties[childName] = childSchema;
      });
    }
    const objSchema: any = {
      type: 'object',
      properties,
      additionalProperties: false,
    };
    if (required.length) objSchema.required = required;
    return objSchema;
  };

  const buildNode = (node: EntityTreeNode): any => {
    const wrapper: any = node.Entity as any;
    if (isArrayEntity(wrapper)) {
      return {
        type: 'array',
        items: buildEntitySchema(node),
        minItems: 0,
      };
    }
    return buildEntitySchema(node);
  };

  const rootNamesCounter = new Map<string, number>();
  const rootProperties: Record<string, any> = {};
  tree.forEach(rootNode => {
    const rootWrapper: any = rootNode.Entity as any;
    const meta = rootWrapper.Entity?.Id ? rootWrapper.Entity : rootWrapper;
    let rootName = meta.Name || meta.UniqueName || `Entity_${rootNode.EntityId}`;
    if (rootProperties[rootName] !== undefined) {
      const idx = (rootNamesCounter.get(rootName) || 0) + 1;
      rootNamesCounter.set(rootName, idx);
      rootName = `${rootName}_${idx}`;
    } else {
      rootNamesCounter.set(rootName, 0);
    }
    rootProperties[rootName] = buildNode(rootNode);
  });

  return {
    $schema: 'https://json-schema.org/draft/2020-12/schema',
    type: 'object',
    properties: rootProperties,
    additionalProperties: false,
  };
}

/**
 * Generate sample data from a JSON Schema object (draft 2020-12 style or similar).
 *
 * This is a schema-driven counterpart to generateSampleRecords().
 * It intentionally keeps generation predictable and shallow while still producing
 * representative shape samples:
 *  - object: populate each property (recursing) and include required props.
 *  - array: produce `options.arrayCount` root elements (default 1) and exactly 1 element for nested arrays.
 *  - string/integer/number/boolean/date-time: lightweight faker-backed examples.
 *  - enum: pick a random allowed value.
 *  - oneOf/anyOf/allOf: pick the first resolvable branch (simple heuristic).
 *  - $ref (internal): if schema.definitions or components.schemas is present, it resolves basic local refs (#/definitions/Name or #/components/schemas/Name).
 */
export function generateSampleDataFromSchema(
  schema: any,
  options?: { arrayCount?: number; depthLimit?: number }
): any {
  const arrayRootCount = Math.max(1, Math.min(options?.arrayCount ?? 1, 25));
  const depthLimit = Math.max(1, Math.min(options?.depthLimit ?? 12, 50));

  // Basic ref resolver (internal only)
  const resolveRef = (ref: string): any => {
    if (!ref.startsWith('#/')) return {}; // unsupported external refs
    const path = ref.replace(/^#\//, '').split('/');
    let cur: any = schema;
    for (const seg of path) {
      if (cur && typeof cur === 'object') cur = cur[seg]; else return {};
    }
    return cur;
  };

  const rand = (min: number, max: number) => min + Math.floor(Math.random() * (max - min + 1));

  const genPrimitive = (sch: any, keyName?: string): any => {
    if (sch && Array.isArray(sch.enum) && sch.enum.length) {
      return sch.enum[rand(0, sch.enum.length - 1)];
    }
    const fmt = sch?.format;
    switch (sch?.type) {
      case 'integer':
        return faker.number.int({ min: 0, max: 1000 });
      case 'number':
        return faker.number.float({ min: 0, max: 1000, fractionDigits: 2 });
      case 'boolean':
        return faker.datatype.boolean();
      case 'string': {
        if (fmt === 'date-time') return faker.date.recent({ days: 30 }).toISOString();
        const k = (keyName || '').toLowerCase();
        if (k.includes('id')) return faker.string.uuid();
        if (k.includes('email')) return faker.internet.email();
        if (k.includes('name')) return faker.person.fullName();
        if (k.includes('url')) return faker.internet.url();
        if (k.includes('date')) return faker.date.recent().toISOString();
        return faker.lorem.word();
      }
      default:
        return null;
    }
  };

  const chooseComposite = (sch: any): any => {
    if (Array.isArray(sch.oneOf) && sch.oneOf.length) return sch.oneOf[0];
    if (Array.isArray(sch.anyOf) && sch.anyOf.length) return sch.anyOf[0];
    if (Array.isArray(sch.allOf) && sch.allOf.length) {
      // Merge shallowly (later objects override earlier)
      return sch.allOf.reduce((acc: any, part: any) => ({ ...acc, ...part }), {});
    }
    return sch;
  };

  // isTopLevelArray indicates either the schema itself is an array OR an array that is a direct child of the root object.
  const build = (sch: any, depth: number, keyName?: string, isTopLevelArray = false): any => {
    if (!sch || depth > depthLimit) return null;
    if (sch.$ref) return build(resolveRef(sch.$ref), depth + 1, keyName, isTopLevelArray);
    sch = chooseComposite(sch);
    if (Array.isArray(sch.type)) {
      // prefer first non-null type
      const primary = sch.type.find((t: string) => t !== 'null') || sch.type[0];
      sch = { ...sch, type: primary };
    }
    switch (sch.type) {
      case 'object': {
        const obj: any = {};
        const props = sch.properties || {};
        Object.keys(props).forEach(propKey => {
          // Arrays that are direct children of the root object (depth === 0 for root, so child depth === 1)
          const childSchema = props[propKey];
          const childIsTopLevelArray = depth === 0 && childSchema && (childSchema.type === 'array' || (Array.isArray(childSchema.type) && childSchema.type.includes('array')));
          obj[propKey] = build(childSchema, depth + 1, propKey, childIsTopLevelArray);
        });
        return obj;
      }
      case 'array': {
        const items = sch.items || {};
        const count = isTopLevelArray ? arrayRootCount : 1;
        const arr: any[] = [];
        for (let i = 0; i < count; i++) arr.push(build(items, depth + 1, keyName, false));
        return arr;
      }
      case 'string':
      case 'integer':
      case 'number':
      case 'boolean':
        return genPrimitive(sch, keyName);
      case 'null':
        return null;
      default: {
        // fallback: attempt properties/items
        if (sch.properties) return build({ ...sch, type: 'object' }, depth + 1, keyName, isTopLevelArray);
        if (sch.items) return build({ ...sch, type: 'array' }, depth + 1, keyName, isTopLevelArray);
        return genPrimitive({ type: 'string' }, keyName);
      }
    }
  };

  return build(schema, 0, undefined, schema?.type === 'array');
}


// export const getModelEntityAssociations = async (modelId: number) => {
//   try {
//     const response = await api.get<EntityAssociation>(
//       `${apiBaseUrl}/entity_associations/by_data_model_id/${modelId}?page=1&pagination=false&check_base=true`
//     );
//     return response.data;
//   } catch (error) {
//     console.error("Error fetching entity associations:", error);
//     throw error;
//   }
// };

export const getModelValueSets = async (modelId: number) => {
  try {
    const response = await api.get<CountResponse>(
      `${apiBaseUrl}/value_sets/by_data_model_id/${modelId}?page=1&pagination=false&check_base=true`
    );
    return response.data.data;
    // return {
    //   valuesets: response.data.data,
    //   count: response.data.total,
    // };
  } catch (error) {
    console.error("Error fetching value sets:", error);
    throw error;
  }
};

export const getModelConstraints = async (modelId: number) => {
  try {
    const response = await api.get(
      `${apiBaseUrl}/datamodel_constraints/by_data_model_id/${modelId}?page=1&size=10&pagination=false`
    );
    return response.data;
  } catch (error) {
    console.error("!!!Error fetching model constraints:", error);
    throw error;
  }
};

/**
 * Fetch OrgLIF extension data models.
 * Optional filters:
 *  - contributor_organization: string
 *  - state: string (matches backend StateType values)
 * Returns a plain list of DataModel (no ApiResponse wrapper).
 */
export const listOrgLifModels = async (
  filters?: { contributor_organization?: string; state?: StateType }
): Promise<DataModel[]> => {
  try {
    const response = await api.get<DataModel[]>(`${apiBaseUrl}/datamodels/orglif/`, {
      params: {
        contributor_organization: filters?.contributor_organization,
        state: filters?.state,
      },
      // Avoid sending undefined params
      paramsSerializer: {
        serialize: (params) => {
          const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && String(v).length > 0);
          const usp = new URLSearchParams(entries as [string, string][]);
          return usp.toString();
        },
      },
    });
    return response.data ?? [];
  } catch (error) {
    console.error("Error fetching OrgLIF data models:", error);
    throw error;
  }
};

export interface CreateDataModelParams {
  Name: string;
  Description?: string;
  UseConsiderations?: string;
  Type: "SourceSchema" | "PartnerLIF";
  BaseDataModelId?: number;
  DataModelVersion: string;
  Notes?: string;
  Contributor?: string;
  ContributorOrganization?: string;
  LevelOfAccess?: "Public" | "Private";
  State?: "Draft" | "Published";
  Tags?: string;
  CreationDate?: string;
  ActivationDate?: string;
  DeprecationDate?: string;
  File?: File | null; // for uploads
}

export const createDataModel = async (params: CreateDataModelParams) => {
  try {
    const response = await api.post(`${apiBaseUrl}/datamodels/`, params);
    return response.data;
  } catch (error) {
    console.error("Error creating data model:", error);
    throw error;
  }
};

export const createDataModelFromUpload = async (params: CreateDataModelParams) => {
  try {
    const { File, ...rest } = params;
    if (!File) {
      throw new Error("File is required when uploading a data model schema.");
    }

    const formData = new FormData();
    formData.append("file", File);

    const restRecord = rest as Record<string, unknown>;
    const appendIfPresent = (formKey: string, value: unknown) => {
      if (value !== undefined && value !== null && value !== "") {
        formData.append(formKey, String(value));
      }
    };

    appendIfPresent("data_model_type", restRecord.Type);
    appendIfPresent(
      "use_considerations",
      restRecord.UseConsiderations ?? restRecord["Use Considerations"]
    );
    appendIfPresent("notes", restRecord.Notes);
    appendIfPresent("activation_date", restRecord.ActivationDate);
    appendIfPresent("deprecation_date", restRecord.DeprecationDate);
    appendIfPresent("contributor", restRecord.Contributor);
    appendIfPresent(
      "contributor_organization",
      restRecord.ContributorOrganization
    );
    appendIfPresent("data_model_name", restRecord.Name);
    appendIfPresent("data_model_version", restRecord.DataModelVersion);
    appendIfPresent("data_model_description", restRecord.Description);
    appendIfPresent("base_data_model_id", restRecord.BaseDataModelId);
    appendIfPresent("state", restRecord.State);
    appendIfPresent("tags", restRecord.Tags);

    const response = await api.post(
      `${apiBaseUrl}/datamodels/open_api_schema/upload`,
      formData,
      {
        headers: { "Content-Type": "multipart/form-data" },
      }
    );
    return response.data;
  } catch (error) {
    console.error("Error creating data model from upload:", error);
    throw error;
  }
};

export const updateDataModel = async (id: number, params: Partial<CreateDataModelParams>) => {
  try {
    const response = await api.put(`${apiBaseUrl}/datamodels/${id}`, params);
    return response.data;
  } catch (error) {
    console.error("Error updating data model:", error);
    throw error;
  }
};


export const updateDataModelFromUpload = async (id: number, params: CreateDataModelParams) => {
  try {
    const { File, ...rest } = params;
    if (!File) {
      throw new Error("File is required when uploading a data model schema.");
    }

    const formData = new FormData();
    formData.append("file", File);

    const restRecord = rest as Record<string, unknown>;
    const appendIfPresent = (formKey: string, value: unknown) => {
      if (value !== undefined && value !== null && value !== "") {
        formData.append(formKey, String(value));
      }
    };

    appendIfPresent(
      "use_considerations",
      restRecord.UseConsiderations ?? restRecord["Use Considerations"]
    );
    appendIfPresent("notes", restRecord.Notes);
    appendIfPresent("activation_date", restRecord.ActivationDate);
    appendIfPresent("deprecation_date", restRecord.DeprecationDate);
    appendIfPresent("contributor", restRecord.Contributor);
    appendIfPresent(
      "contributor_organization",
      restRecord.ContributorOrganization
    );
    appendIfPresent("data_model_name", restRecord.Name);
    appendIfPresent("data_model_version", restRecord.DataModelVersion);
    appendIfPresent("data_model_description", restRecord.Description);
    appendIfPresent("state", restRecord.State);
    appendIfPresent("tags", restRecord.Tags);

    const response = await api.put(
      `${apiBaseUrl}/datamodels/${id}/use_schema_upload`,
      formData,
      {
        headers: { "Content-Type": "multipart/form-data" },
      }
    );
    return response.data;
  } catch (error) {
    console.error("Error updating data model from upload:", error);
    throw error;
  }
};

export const deleteDataModel = async (id: number) => {
  try {
    const response = await api.delete(`${apiBaseUrl}/datamodels/${id}`);
    return response.data;
  } catch (error) {
    console.error("Error deleting data model:", error);
    throw error;
  }
};

export interface ConstraintDTO {
  Id: number;
  Name: string;
  Description: string | null;
  ForDataModelId: number;
  ElementType: "Entity" | "Attribute" | "ValueSet";
  ElementId: number;
  ElementName: string;
  ConstraintType: string | null;
  Notes: string | null;
  CreationDate: string | null;
  ActivationDate: string | null;
  DeprecationDate: string | null;
  Contributor: string | null;
  ContributorOrganization: string | null;
  Deleted: boolean;
}

export interface CreateConstraintParams {
  Name: string;
  Description?: string | null;
  ForDataModelId: number;
  ElementType: "Entity" | "Attribute" | "ValueSet";
  ElementId: number;
  Notes?: string | null;
  Contributor?: string | null;
  ContributorOrganization?: string | null;
}


export const getOpenApiSchema = async (id: number, pub?: boolean, mdEnt?: boolean, mdAttr?: boolean, mdFull?: boolean, blob?: boolean) => {
  const params = [
    blob ? `download=true` : '',
    pub ? `public_only=true` : '',
    mdEnt ? `include_entity_md=${mdEnt}` : '',
    mdAttr ? `include_attr_md=${mdAttr}` : '',
    mdFull ? `full_export=${mdFull}` : '',
  ].filter(Boolean);
  const query = params.length ? `?${params.join('&')}` : '';
  let result: any = {};
  try {
    result = await api.get<ApiResponse>(`${apiBaseUrl}/datamodels/open_api_schema/${id}${query}`, { responseType: blob ? 'blob' : 'json' });
    // console.log("getOpenApiSchema result:", result);
    return result.data;
  } catch (error) {
    console.error("Error fetching data:", error);
    throw error;
  }
};

export const downloadOpenApiSchema = async (id: number, type?: string, pub?: boolean) => {
  type = type?.length && ['full', 'legacy', 'bare'].includes(type) ? type : 'full';
  let mdEnt = false;
  let mdAttr = false;
  let mdFull = false;
  switch (type) {
    case 'full': mdEnt = true; mdAttr = true; mdFull = true; break;
    case 'legacy': mdAttr = true; break;
    default: break;
  }
  const fileName = `data_model_${id}_${type}_openapi_schema.json`;
  const result = await getOpenApiSchema(id, pub, mdEnt, mdAttr, mdFull, true);
  if (result) {
    const link = document.createElement('a');
    const url = window.URL.createObjectURL(result);
    link.href = url;
    link.setAttribute('type', 'hidden');
    link.setAttribute('download', fileName);
    document.body.appendChild(link);
    link.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(link);
  } else {
    console.error("No data received for file download.");
  }
};
