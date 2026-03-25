import { Box, Dialog, Spinner } from "@radix-ui/themes";
import { Pencil2Icon, TrashIcon, FileTextIcon, LinkBreak2Icon, CardStackMinusIcon, DashIcon } from "@radix-ui/react-icons";
import React, { useMemo, useEffect, useState, useCallback, useRef } from "react";
import { useNavigate, useParams, useLocation } from "react-router-dom";
import { CrudDialog, DeleteDialog, SelectDialog, SimpleAlertDialog } from "../Dialog/Dialog";
import { TreeModelExplorer, transformData } from "./TreeModelExplorer";
import ObjectDetails from "../ObjectDetails/ObjectDetails";
import { useToast } from "../../context/ToastContext";
import { errorToString } from "../../utils/errorUtils";

const FileDEBUG = false;
const debugLog = (...args: any[]) => { if(FileDEBUG) console.log(...args); };
const reportWarn = (...args: any[]) => { console.warn(...args); };
const reportError = (...args: any[]) => { console.error(...args); };
const uniqueValues = (items: any[]) => [...new Set(items)].filter(Boolean);

const updateObjAWithB = (objA: any, objB: any) => {
  if (objA && typeof objA === 'object' && objB && typeof objB === 'object')
    Object.keys(objA).forEach((key) => { if (objB[key]) { objA[key] = objB[key]; } });
  return objA;
};

import {
  listModels,
  getModel,
  getModelDetails,
  updateDataModel,
  // deleteDataModel,
  CreateDataModelParams,
  downloadOpenApiSchema,
} from "../../services/modelService";
import {
  entityCreateFields,
  entityAssociationFields,
  attributeCreateFields,
  attributeAssociationFields,
  valueSetCreateFields,
  valueCreateFields,
  inclusionEditFields,
} from "./CreateOptFields"
import {
  listEntitiesForDataModel,
  createEntity,
  updateEntity,
  deleteEntity,
  EntityParams,
  getModelEntityAssociations,
  getEntityAssociationsByParentId,
  tmplCreateEntityAssociation,
  createEntityAssociation,
  deleteEntityAssociation,
  updateEntityAssociation,
} from "../../services/entityService";
import {
  listInclusionByModel,
  createInclusion,
  updateInclusion,
  deleteInclusion,
  CreateInclusionParams,
  tmplCreateInclusion,
  getInclusion,
} from "../../services/inclusionService";
import {
  listAttributesForDataModel,
  listAttributesByEntity,
  createAttribute,
  updateAttribute,
  deleteAttribute,
  AttributeParams,
  getAttributeEntityAssociationsByAttr,
  getAttributeEntityAssociationsByModel,
  tmplCreateEntityAttributeAssociation,
  createEntityAttributeAssociation,
  deleteEntityAttributeAssociation,
  updateEntityAttributeAssociation,
} from "../../services/attributesService";
import {
  listValueSetsForDataModel,
  createValueSet,
  updateValueSet,
  deleteValueSet,
  ValueSetParams,
} from "../../services/valueSetService";
import {
  createValue,
  updateValue,
  deleteValue,
  ValueParams,
} from "../../services/valueService";


interface ModelTreeProps {
  crud: boolean;
  model: any;
  routPath: string;
  onEditModel: (id: number, params: any) => Promise<void>;
  ContribUser?: string;
  ContribOrg?: string;
}

const ModelTree: React.FC<ModelTreeProps> = ({ 
  crud = false,
  model,
  routPath,
  onEditModel,
  ContribUser,
  ContribOrg,
}) => {
  const { showToast } = useToast();
  const navigate = useNavigate();
  const location = useLocation();
  const { entityId, valueSetId, valueId, attributeId } = useParams();
  const [loading, setLoading] = useState<boolean>(false);
  const [useInclusion, setUseInclusion] = useState<boolean>(false);
  // Data model lists
  const [baseModel, setBaseModel] = useState<any | null>(null);
  const [entities, setEntities] = useState<any[] | null>(null);
  const [attributes, setAttributes] = useState<any>([]);
  const [valueSets, setValueSets] = useState<any>([]);
  const [valueSetValues, setValueSetValues] = useState<any>([]);
  const [allEAs, setAllEAs] = useState<any[]>([]);
  const [allEAAs, setAllEAAs] = useState<any[]>([]);
  // Selected model items
  const [selectedModel, setSelectedModel] = useState<any>(null);
  const [selectedEntity, setSelectedEntity] = useState<any>(entityId || null);
  const [selectedAttribute, setSelectedAttribute] = useState<any>(attributeId || null);
  const [selectedValueSet, setSelectedValueSet] = useState<any>(valueSetId || null);
  const [selectedValue, setSelectedValue] = useState<any>(valueId ||null);
  const [propDetails, setPropDetails] = useState<any>(null);
  // TreeModelExplorer variables
  const [treeHeader, setTreeHeader] = useState<string>("");
  const [selectedType, setSelectedType] = useState<string>("");
  const [selectedNode, setSelectedNode] = useState<any>(null);
  const [showInclusionToggles, setShowInclusionToggles] = useState<boolean>(false);
  const [showPublicToggles, setShowPublicToggles] = useState<boolean>(false);

  const propNotFound = { Id: -1, Name: "Oops, something went wrong.", Value: "Error" };
  const capitalize = (s: string): string => { return s?.length ? s.charAt(0).toUpperCase() + s.slice(1) : ""; }

  const alertDialog = (title: string, msg: string) => {
    const newDialogOptions = { alertDialog: true, title: title, message: msg };
    setDialogOptions(newDialogOptions);
  };


  const fetchData = useCallback(async () => {
    debugLog("fetchData()...");
    setLoading(true);

    let fetchInclusion = false;
    let modelData: any = {};
    let useBaseData = false;
    try {
      let modelParams: string = "";
      let modelFilter: string = ""
      if (model.Type === "OrgLIF") {
        if (location.pathname.includes("/only")) {
          modelFilter = " (Only)";
        } else if (location.pathname.includes("/public")) {
          modelParams = "public_only=true";
          modelFilter = " (Public)";
        } else if (location.pathname.includes("/extension")) {
          modelParams = "org_ext_only=true";
          modelFilter = " (Extension)";
        } else if (location.pathname.includes("/partner")) {
          modelParams = "partner_only=true";
          modelFilter = " (Partner)";
        } else { // /:id or /:id/base
          modelFilter = " (Inclusions)";
        }
      }      
      modelData = await getModelDetails(model.Id, modelParams);
      const dModel = modelData?.DataModel;
      const isOrganizationView = location.pathname.includes("/only");
      useBaseData = dModel?.Type === "OrgLIF" && modelParams === "" && !isOrganizationView;
      debugLog(" -Model:", dModel);
      fetchInclusion = ["OrgLIF", "PartnerLIF"].includes(dModel?.Type);
      setUseInclusion(fetchInclusion);
      setShowPublicToggles(fetchInclusion && modelParams === "");
      setShowInclusionToggles(fetchInclusion && modelParams === "" && !isOrganizationView);
      setTreeHeader(`${dModel?.Name || '404'}${modelFilter}`)
      setSelectedType("Data Model");
      setPropDetails(dModel || null);
      setSelectedNode(null);
    } catch (error) {
      reportError("Error fetching model details:", errorToString(error));
      setSelectedModel(null);
      return;
    }

    let baseData: any = {};
    modelData.Inclusions = [];
    modelData.EntityAssociations = [];
    modelData.AttributeAssociations = [];
    baseData.EntityAssociations = [];
    baseData.AttributeAssociations = [];
    if (modelData && fetchInclusion) {
      if (useBaseData) {
        try {
          // get BaseLIF model details
          baseData = await getModelDetails(1); // BaseLIF is always ID=1
          debugLog(" -BaseLIF Model:", baseData?.DataModel);
          // get Entity Associations for base model
          const entityAssociations: any = await getModelEntityAssociations(1);
          debugLog(" -baseData Entity Associations:", entityAssociations?.length);
          baseData.EntityAssociations = entityAssociations || [];
          // get Attribute Associations for base model
          const attrAssociations: any = await getAttributeEntityAssociationsByModel(1);
          debugLog(" -baseData Attribute Associations:", attrAssociations?.length);
          baseData.AttributeAssociations = attrAssociations || [];
          // set baseModel
        } catch (error) {
          reportError("Error fetching BaseLIF model details:", errorToString(error));
          return;
        }
      }

      try { // get Inclusions
        const modelInclusions: any = await listInclusionByModel(model.Id);
        debugLog(" -Inclusions:", modelInclusions.length);
        modelData.Inclusions = modelInclusions || [];
      } catch (error) {
        modelData.Inclusions = [];
        reportError("Error fetching inclusions:", errorToString(error));
      }
    } else {
      modelData.Inclusions = [];
      setBaseModel(null);
      debugLog(" -No Inclusions or EntityAssociations (not OrgLIF or PartnerLIF)");
    }

    try { // get Entities
      const modelEntities = await listEntitiesForDataModel(model.Id);
      const baseEntities = useBaseData ? await listEntitiesForDataModel(1) : [];
      const allEntities = [...(modelEntities || []), ...(baseEntities || [])];
      const uniqueEntities = allEntities.filter((e, idx, arr) => 
        e.Id && arr.findIndex(entity => entity.Id === e.Id) === idx
      );
      debugLog(` - ${uniqueEntities.length} Unique Entities: ${modelEntities.length} model, ${baseEntities.length} BaseLIF`);
      setEntities(uniqueEntities);
    } catch (error) {
      reportError("Error fetching entities:", errorToString(error));
      setEntities([]);
    }

    modelData.EntityAssociations = [];
    try { // get Entity Associations
      const entityAssociations: any = await getModelEntityAssociations(model.Id);
      debugLog(" -Entity Associations:", entityAssociations?.length);
      modelData.EntityAssociations = entityAssociations || [];
    } catch (error) {
      reportError("Error fetching entity associations:", errorToString(error));
    }

    try { // get Attributes
      const modelAttrs = await listAttributesForDataModel(model.Id);
      const baseAttrs = useBaseData ? await listAttributesForDataModel(1) : [];
      const allAttrs = [...(modelAttrs || []), ...(baseAttrs || [])];
      const uniqueAttrs = allAttrs.filter((e, idx, arr) => 
        e.Id && arr.findIndex(entity => entity.Id === e.Id) === idx
      );
      debugLog(` - ${uniqueAttrs.length} Unique Attributes: ${modelAttrs.length} model, ${baseAttrs.length} BaseLIF`);
      setAttributes(uniqueAttrs);
    } catch (error) {
      reportError("Error fetching attributes:", errorToString(error));
      setAttributes([]);
    }

    modelData.AttributeAssociations = [];
    try { // get Attribute Associations
      const attrAssociations: any = await getAttributeEntityAssociationsByModel(model.Id);
      debugLog(" -Attribute Associations:", attrAssociations?.length);
      modelData.AttributeAssociations = attrAssociations || [];
    } catch (error) {
      reportError("Error fetching attribute associations:", errorToString(error));
    }

    try { // get Value Sets
      const uniqueValueSets: any[] = [];
      modelData?.ValueSets?.forEach((vs: any) => {
        if (vs.ValueSet?.Id && !uniqueValueSets.find(e => e.Id === vs.ValueSet.Id)) {
          uniqueValueSets.push(vs.ValueSet);
        }
      });
      baseData?.ValueSets?.forEach((vs: any) => {
        if (vs.ValueSet?.Id && !uniqueValueSets.find(e => e.Id === vs.ValueSet.Id)) {
          uniqueValueSets.push(vs.ValueSet);
        }
      });
      debugLog(" -ValueSets:", uniqueValueSets.length);
      setValueSets(uniqueValueSets);
    } catch (error) {
      reportError("Error fetching value sets:", errorToString(error));
      setValueSets([]);
    }

    setAllEAs(uniqueValues([...(baseData?.EntityAssociations || []), ...(modelData?.EntityAssociations || [])]));
    setAllEAAs(uniqueValues([...(baseData?.AttributeAssociations || []), ...(modelData?.AttributeAssociations || [])]));

    React.startTransition(() => {
      setSelectedModel(modelData);
      setBaseModel(baseData || null);
      setLoading(false);
    });
    debugLog("fetchData() completed!");
  }, [model]);


  const onNodeSelect = (node: any, parentNode?: any) => {
    node.parentNode = parentNode || {};
    debugLog("onNodeSelect:", node);
    setSelectedNode(node.type === 'model' ? null : node);
  };

  const onModelSelect = async () => {
    setSelectedType("Data Model");
    setPropDetails(selectedModel?.DataModel || propNotFound);
    debugLog("onModelSelect:", selectedModel?.Id, selectedModel?.DataModel);
  };

  const onEntitySelect = async (id: number) => {
    const selectObj = entities?.find((e: any) => e.Id === id) || propNotFound;
    setSelectedType("Entity");
    setPropDetails(selectObj);
    // setSelectedEntity(selectObj.Id || null);
    debugLog("onEntitySelect:", id, selectObj);
  };

  const onAttributeSelect = async (id: number) => {
    const selectObj = attributes?.find((attr: any) => attr.Id === id) || propNotFound;
    setSelectedType("Attribute");
    setPropDetails(selectObj);
    // setSelectedAttribute(selectObj.Id || null);
    debugLog("onAttributeSelect:", id, selectObj);
  };

  const onValueSetSelect = async (id: number, clicked: boolean = false) => {
    const selectObj = valueSets?.find((vs: any) => vs.Id === id) || propNotFound;
    setSelectedType("Value Set");
    setPropDetails(selectObj);
    // setSelectedValueSet(selectObj.Id || null);
    debugLog("onValueSetSelect:", id, selectObj);
  };

  const onValueSelect = (id: number, valueSetId: number) => {
    // if (valueSetId) setSelectedValueSet(valueSetId);
    const setObj = selectedModel?.ValueSets?.find((vs: any) => vs.ValueSet?.Id === valueSetId) || propNotFound;
    const selectObj = setObj.Values?.find((val: any) => val.Id === id) || propNotFound;
    setSelectedType("Value");
    setPropDetails(selectObj);
    // setSelectedValue(selectObj.Id || null);
    debugLog(`onValueSelect(id: ${id} => ${selectObj?.Id}, valueSetId: ${valueSetId} => ${setObj?.ValueSet?.Id})`);
  };


  const handleOnAddNew = async (modelNode: any) => {
    await handleCreateDropdown(modelNode, 'entity');
  };

  const handleCreateEntity = async (params: EntityParams, parentNode?: any) => {
    debugLog("Creating Entity:", params, parentNode);
    // update the contributor information if empty
    params.Contributor = params.Contributor || ContribUser;
    params.ContributorOrganization = params.ContributorOrganization || ContribOrg;
    // prepare for new entity relationships
    const useEntityAssociation = parentNode?.type === 'entity';
    const inclusionParams: any = useInclusion ? tmplCreateInclusion(model.Id, 0, 'Entity') : {};
    const entityAssociationParams: any = useEntityAssociation ? tmplCreateEntityAssociation(parentNode.id, model) : {};

    const createdIds: any = {};
    try {
      const newEntity: any = await createEntity({ ...params, DataModelId: model.Id });
      createdIds.Entity = newEntity?.Id;
      debugLog(">> Created Entity:", newEntity?.Id, newEntity);
      if (newEntity?.Id && useEntityAssociation) {
        entityAssociationParams.ChildEntityId = newEntity?.Id;
        entityAssociationParams.Contributor = params.Contributor; //reusing dialog fields if possible
        entityAssociationParams.ContributorOrganization = params.ContributorOrganization;
      }
      if (newEntity?.Id && useEntityAssociation) {
        const newEntityAssociation: any = await createEntityAssociation(entityAssociationParams);
        createdIds.EntityAssociation = newEntityAssociation?.Id;
        debugLog(">> Created Entity Association:", newEntityAssociation?.Id, newEntityAssociation);
      }
      if (newEntity?.Id && useInclusion) {
        inclusionParams.IncludedElementId = newEntity?.Id;
        inclusionParams.Contributor = params.Contributor; //reusing dialog fields if possible
        inclusionParams.ContributorOrganization = params.ContributorOrganization;
        const newInclusion: any = await createInclusion(inclusionParams);
        createdIds.Inclusion = newInclusion?.Id;
        debugLog(">> Created Inclusion:", newInclusion?.Id, newInclusion);
      }
    } catch (error) {
      reportError("Error creating entity and associations:", createdIds, errorToString(error));
      throw error;
    }
    // If anything was created, refresh the data
    if (Object.keys(createdIds).length) await fetchData();
  };

  const handleCreateAttribute = async (params: AttributeParams, parentNode?: any) => {
    debugLog("Creating Attribute:", params, parentNode);
    // update the contributor information if empty
    params.Contributor = params.Contributor || ContribUser;
    params.ContributorOrganization = params.ContributorOrganization || ContribOrg;
    // prepare for new entity relationships
    const useEAA = parentNode?.type === 'entity';
      /** ^ Always want an association, but should also be under an Entity */
    const inclusionParams: any = useInclusion ? tmplCreateInclusion(model.Id, 0, 'Attribute') : {};
    const eAAParams: any = useEAA ? tmplCreateEntityAttributeAssociation(parentNode.id, model) : {};

    const createdIds: any = {};
    try {
      const newAttribute: any = await createAttribute({ ...params, DataModelId: model.Id });
      createdIds.Attribute = newAttribute?.Id;
      debugLog(">> Created Attribute:", newAttribute?.Id, newAttribute);
      if (newAttribute?.Id && useEAA) {
        eAAParams.AttributeId = newAttribute?.Id;
        eAAParams.Contributor = params.Contributor;
        eAAParams.ContributorOrganization = params.ContributorOrganization;
        const newEAA: any = await createEntityAttributeAssociation(eAAParams);
        createdIds.EntityAttributeAssociation = newEAA?.Id;
        debugLog(">> Created Entity Attribute Association:", newEAA?.Id, newEAA);
      }
      if (newAttribute?.Id && useInclusion) {
        inclusionParams.IncludedElementId = newAttribute?.Id;
        inclusionParams.Contributor = params.Contributor;
        inclusionParams.ContributorOrganization = params.ContributorOrganization;
        const newInclusion: any = await createInclusion(inclusionParams);
        createdIds.Inclusion = newInclusion?.Id;
        debugLog(">> Created Inclusion:", newInclusion?.Id, newInclusion);
      }
    } catch (error) {
      reportError("Error creating attribute and associations:", createdIds, errorToString(error));
      throw error;
    }
    // If anything was created, refresh the data
    if (Object.keys(createdIds).length) await fetchData();
  };

  const handleCreateValueSet = async (params: ValueSetParams, parentNode?: any) => {
    // update the contributor information if empty
    params.Contributor = params.Contributor || ContribUser;
    params.ContributorOrganization = params.ContributorOrganization || ContribOrg;
    debugLog("Creating Value Set:", params, parentNode);

    const createdIds: any = {};
    try {
      const newValueSet: any = await createValueSet({ ...params, DataModelId: model.Id });
      createdIds.ValueSet = newValueSet?.Id;
      debugLog(">> Created Value Set:", createdIds.ValueSet, newValueSet);
      if (createdIds.ValueSet && parentNode?.type === 'attribute' && parentNode?.id) {
        // should already have tested against the parentNode before, but just in case
        const updatedAttribute: any = await updateAttribute(parentNode.id, { ValueSetId: createdIds.ValueSet } as AttributeParams);
        debugLog(">> Updated Attribute with ValueSetId:", parentNode.id, updatedAttribute);
      }
    } catch (error) {
      reportError("Error creating value set and updating attribute:", createdIds, errorToString(error));
      throw error;
    }
    // If anything was created, refresh the data
    if (Object.keys(createdIds).length) await fetchData();
  };

  const handleCreateValue = async (params: any, parentNode?: any) => {
    const valueSetId = parentNode?.type === 'valueSet' ? parentNode.id : undefined;
    params.Contributor = params.Contributor || ContribUser;
    params.ContributorOrganization = params.ContributorOrganization || ContribOrg;
    debugLog("Creating Value:", params, parentNode);
  
    try {
      const valueParams: ValueParams = {
        ...params,
        ValueSetId: valueSetId,
        DataModelId: model.Id,
      };
      const newValue: any = await createValue(valueParams);
      debugLog(">> Created Value:", newValue?.Id, newValue);
      if (newValue?.Id) await fetchData();
    } catch (error) {
      reportError("Error creating value:", errorToString(error));
      throw error;
    }
  };


  const [dialogOptions, setDialogOptions] = useState<any>({});
  const [isCrudDialogOpen, setIsCrudDialogOpen] = useState(false);
  const handleDialogOpenChange = (open: boolean) => {
    setIsCrudDialogOpen(open);
    if (!open) setDialogOptions({});
  };

  // HANDLE CREATE CRUD DIALOG
  const handleCreateDropdown = async (node: any, kind: string) => {
    debugLog("handleCreateDropdown", kind, node);
    let newDialogOptions: any = { isEditMode: false, fields: [] };

    const valueSetId = node.parentType === "valueSet" ? node.parentId || undefined : undefined;
    switch(kind) {
      case "entity":
        if (!['entity', 'model'].includes(node.type) || !node.id) {
          reportError("Entity must be created under an Entity or Model, not:", node);
          return;
        }
        newDialogOptions.title = "Entity";
        newDialogOptions.fields = entityCreateFields(model);
        newDialogOptions.onCreate = (params: EntityParams) => handleCreateEntity(params, node);
        break;
      case "attribute":
        if (!['entity'].includes(node.type) || !node.id) {
          reportError("Attribute must be created under an Entity, not:", node);
          return;
        }
        newDialogOptions.title = "Attribute";
        newDialogOptions.fields = attributeCreateFields(model, valueSetId);
        newDialogOptions.onCreate = (params: AttributeParams) => handleCreateAttribute(params, node);
        break;
      case "valueSet":
        if (node.type !== 'attribute' || !node.id) {
          reportError("Value Set must be created under an Attribute, not:", node);
          return;
        }
        newDialogOptions.title = "Value Set";
        newDialogOptions.fields = valueSetCreateFields(model);
        newDialogOptions.onCreate = (params: ValueSetParams) => handleCreateValueSet(params, node);
        break;
      case "value":
        if (node.type !== 'valueSet' || !node.id) {
          reportError("Value must be created under a Value Set, not:", node);
          return;
        }
        newDialogOptions.title = "Value";
        newDialogOptions.fields = valueCreateFields(model);
        newDialogOptions.onCreate = (params: ValueParams) => handleCreateValue(params, node);
        break;
      default:
        return;
    }
    setDialogOptions(newDialogOptions);
    setIsCrudDialogOpen(true);
  };

  // HANDLE EDIT CRUD DIALOG
  const handleEditItem = (item: any) => async () => {
    debugLog("Editing item:", item);
    let newDialogOptions: any = { isEditMode: true, itemToEdit: item, fields: [] };

    const itemNode = selectedNode;
    switch(itemNode?.type) {
      case "entity":
        newDialogOptions.fields = entityCreateFields(model);
        newDialogOptions.onEdit = async (id: number, params: EntityParams) => {
          debugLog("Updating entity:", params);
          const resp: any = await updateEntity(item.Id, params);
          if (resp?.Id) { await fetchData(); }
        };
        break;
      case "attribute":
        newDialogOptions.fields = attributeCreateFields(model, item.ValueSetId);
        newDialogOptions.onEdit = async (id: number, params: AttributeParams) => {
          debugLog("Updating attribute:", params);
          const resp: any = await updateAttribute(item.Id, params);
          if (resp?.Id) { await fetchData(); }
        };
        break;
      case "valueSet":
        newDialogOptions.fields = valueSetCreateFields(model);
        newDialogOptions.onEdit = async (id: number, params: ValueSetParams) => {
          debugLog("Updating value set:", params);
          const resp: any = await updateValueSet(item.Id, params);
          if (resp?.Id) { await fetchData(); }
        };
        break;
      case "value":
        newDialogOptions.fields = valueCreateFields(model);
        newDialogOptions.onEdit = async (id: number, params: ValueParams) => {
          debugLog("Updating value:", params);
          const resp: any = await updateValue(item.Id, params);
          if (resp?.Id) { await fetchData(); }
        };
        break;
      default:
        alertDialog("Edit Dialog Error", `Unhandled edit ${itemNode.type}#${itemNode.id}.`);
        return;
    }
    
    if (!newDialogOptions.fields?.length) {
      debugLog("No fields for editing, aborting.");
      return;
    } else {
      debugLog("Editing dialog options:", newDialogOptions);
      setDialogOptions(newDialogOptions);
      setIsCrudDialogOpen(true);
    }
  };

  const handleEditAssoc = (n: any) => async () => {
    debugLog("handleEditAssoc:", n);
    let errMsg = "";
    if (!n || !n.type || !['entity', 'attribute'].includes(n.type)) errMsg = `Can only edit associations for entity or attribute types, not: ${n?.type}`;
    else if (!n.hasAssocId) errMsg = `No association ID found for ${n.type}#${n.id} to edit.`;
    if (errMsg.length) { alertDialog("Edit Association Error", errMsg); return; }

    let newDialogOptions: any = { isEditMode: true, fields: [] };
    const capitalizedType = capitalize(n.type);
    const All_Assoc = n.type === "entity"
      ? allEAs.filter((ea: any) => ea.ChildEntityId === n.id)
      : allEAAs.filter((eaa: any) => eaa.AttributeId === n.id);
    const selectedAssoc = All_Assoc.find((i: any) => i.Id === n.hasAssocId
      && (n.type === "entity" ? i.ParentEntityId === n.parentId : i.EntityId === n.parentId));
    debugLog(` > ${capitalizedType}#${n.id} Association#${n.hasAssocId} to edit:`, selectedAssoc);
    if (!selectedAssoc || !selectedAssoc.Id) {
      alertDialog("Edit Association Error", `Unable to find the association for ${capitalizedType}#${n.id} to edit.`);
      return;
    }

    if (n.type === "entity") {
      newDialogOptions.itemToEdit = selectedAssoc;
      newDialogOptions.itemToEdit.Name = n.label; // for display in dialog
      newDialogOptions.fields = entityAssociationFields(model);
      newDialogOptions.onEdit = async (id: number, params: EntityParams) => {
        debugLog(` > Updating EA#${id} with params:`, params);
        const resp: any = await updateEntityAssociation(id, params);
        if (resp?.Id) { await fetchData(); }
      };
    } else if (n.type === "attribute") {
      newDialogOptions.itemToEdit = selectedAssoc;
      newDialogOptions.itemToEdit.Name = n.label; // for display in dialog
      newDialogOptions.fields = attributeAssociationFields(model);
      newDialogOptions.onEdit = async (id: number, params: AttributeParams) => {
        debugLog(` > Updating EAA#${id} with params:`, params);
        const resp: any = await updateEntityAttributeAssociation(id, params);
        if (resp?.Id) { await fetchData(); }
      };
    } else {
      alertDialog("Edit Dialog Error", `Unhandled edit association item type '${n.type}#${n.id}'.`);
      return;
    }
    
    if (!newDialogOptions.fields?.length) {
      debugLog("No fields for editing, aborting.");
      return;
    } else {
      debugLog("Editing dialog options:", newDialogOptions);
      setDialogOptions(newDialogOptions);
      setIsCrudDialogOpen(true);
    }
  };

  const handleEditInclusion = (n: any) => async () => {
    debugLog("handleEditInclusion:", n);
    let errMsg = "";
    if (!n || !n.type || !['entity', 'attribute'].includes(n.type)) errMsg = `Can only edit inclusions for entity or attribute types, not: ${n?.type}`;
    else if (!n.hasIncId) errMsg = `No inclusion ID found for ${n.type}#${n.id} to edit.`;
    if (errMsg.length) { alertDialog("Edit Inclusion Error", errMsg); return; }

    let newDialogOptions: any = { isEditMode: true, fields: [] };
    const capitalizedType = capitalize(n.type);
    const hasInc = selectedModel?.Inclusions?.find(
      (i: any) => i.Id === n.hasIncId && i.IncludedElementId === n.id && i.ElementType === capitalizedType && !i.Deleted
    );
    debugLog(` > ${capitalizedType}#${n.id} Inclusion#${n.hasIncId} to edit:`, hasInc);
    if (!hasInc || !hasInc.Id) {
      alertDialog("Edit Inclusion Error", `Unable to find the inclusion for ${capitalizedType}#${n.id} to edit.`);
      return;
    }

    newDialogOptions.itemToEdit = hasInc;
    newDialogOptions.itemToEdit.Name = n.label; // for display in dialog
    newDialogOptions.fields = inclusionEditFields(model);
    newDialogOptions.onEdit = async (id: number, params: Partial<CreateInclusionParams>) => {
      debugLog(` > Updating Inclusion#${id} with params:`, params);
      const resp: any = await updateInclusion(id, params);
      if (resp?.Id) { await fetchData(); }
    };
    
    debugLog("Editing dialog options:", newDialogOptions);
    setDialogOptions(newDialogOptions);
    setIsCrudDialogOpen(true);
  };

  // HANDLE DELETE DIALOG
  const handleDeleteItem = (i: any, delAssoc?: boolean) => async () => {
    const Id = i?.Id;
    const iNode = selectedNode;
    const pNode = selectedNode?.parentNode || {};
    debugLog("handleDeleteItem:", (!!delAssoc ? "association_only" : "complete_object"), i, iNode);
    if(!Id || Id < 1) { reportWarn("Invalid item for deletion:", i); return; }
    if(delAssoc && (!pNode.id || pNode.id < 1)) { reportWarn("Invalid item for association removal:", i, pNode); return; }
    let newDialogOptions: any = {
      itemToDelete: i,
      title: `${!delAssoc ? "Delete" : "Remove"} ${capitalize(iNode?.type)}#${iNode?.id} ${iNode.label}`,
      message: (!delAssoc ? 'Are you sure you want to delete `' + iNode.label + ' for all models?'
        : `Are you sure you want to remove the ${capitalize(iNode.type)} \`${iNode.label}\` association from ${capitalize(pNode.type)} \`${pNode.label}\`?`),
    };
    const ModelInclusions = useInclusion ? [...selectedModel?.Inclusions] : [];
    switch(iNode?.type) {
      case "entity":
        newDialogOptions.onDelete = async () => {
          if (delAssoc) {
            const entityId = iNode?.parentType === 'entity'  ? iNode?.parentId : undefined;
            if (!entityId) { reportError(`Unable to remove entity association for Entity#${iNode.id}`); return; }
            const Entity_EAs = allEAs.filter((ea: any) => ea.ChildEntityId === iNode.id); // all EAs for this entity in this model
            const Only_EA = Entity_EAs.length === 1; // only if single association
            const assocId = Entity_EAs?.find((a: any) => a.ParentEntityId === entityId)?.Id;
            if (!assocId) { reportError(`Unable to find entity association to remove for Entity#${iNode.id}.`); return; }
            const incId = ModelInclusions.find((inc: any) => inc.ElementType === 'Entity' && inc.IncludedElementId === iNode.id)?.Id;
            debugLog(
              ` > Removing ChildEntity#${Id}'s Association#${assocId} from ParentEntity#${entityId}`
              + (Only_EA && incId ? ` as well as Inclusion#${incId}` : '')
            );
            try {
              await deleteEntityAssociation(assocId);
              if (Only_EA && incId) { await deleteInclusion(incId); } // Only if single association left, remove inclusion too
              else { debugLog(` -Skipping Inclusion removal; has ${Entity_EAs.length} instances.`); }
              await fetchData();
            } catch (error) { reportError("Error when removing entity association and inclusion:", errorToString(error)); }
          } else {
            debugLog("Deleting entity:", Id);
            const resp: any = await deleteEntity(Id);
            if(resp?.ok) await fetchData();
          }
        };
        break;
      case "attribute":
        newDialogOptions.onDelete = async () => {
          if (delAssoc) {
            const entityId = iNode?.parentType === 'entity' ? iNode?.parentId : undefined;
            if (!entityId) { reportError(`Unable to remove entity association for Entity#${iNode.id}`); return; }
            const Attr_EAAs: any = allEAAs.filter((eaa: any) => eaa.EntityId === entityId); // all EAAs for this entity in this model
            const Only_EAA = Attr_EAAs.length === 1; // only if single association
            const assocId = Attr_EAAs?.find((a: any) => a.AttributeId === iNode.id)?.Id;
            if (!assocId) { reportError(`Unable to find attribute association to remove Attribute#${iNode.id}.`); return; }
            const incId = ModelInclusions.find((inc: any) => inc.ElementType === 'Attribute' && inc.IncludedElementId === iNode.id)?.Id;
            debugLog(
              ` > Removing Attribute#${Id}'s Association#${assocId} from Entity#${entityId}`
              + (Only_EAA && incId ? ` as well as Inclusion#${incId}` : '')
            );
            try {
              await deleteEntityAttributeAssociation(assocId);
              if (Only_EAA && incId) { await deleteInclusion(incId); } // Only if single association left, remove inclusion too
              else { debugLog(` -Skipping Inclusion removal; has ${Attr_EAAs.length} instances.`); }
              await fetchData();
            } catch (error) { reportError("Error when removing entity association and inclusion:", errorToString(error)); }
          } else {
            debugLog("Deleting attribute:", Id);
            await deleteAttribute(Id);
            await fetchData();
          }
        };
        break;
      case "valueSet":
        newDialogOptions.onDelete = async () => {
          const attrId = iNode?.parentType === 'attribute' ? iNode?.parentId : undefined;
          if (delAssoc) {
            debugLog("Removing value set:", Id, " from attribute:", attrId);
            await updateAttribute(attrId, { ValueSetId: null } as AttributeParams);
            await fetchData();
          } else {
            debugLog("Deleting value set:", Id);
            const resp: any = await deleteValueSet(Id);
            if (resp?.ok) {
              await updateAttribute(attrId, { ValueSetId: null } as AttributeParams);
              await fetchData();
            }
          }
        };
        break;
      case "value":
        if (delAssoc) {
          reportWarn("There are no associations to remove for Value:", i);
          return;
        } else {
          newDialogOptions.onDelete = async () => {
            debugLog("Deleting value:", Id);
            await deleteValue(i?.Id);
            await fetchData();
          };
        }
        break;
      default:
        alertDialog("Delete Dialog Error", `Unhandled delete ${iNode.type}#${iNode.id}.`);
        return;
    }

    if (!newDialogOptions.onDelete) {
      debugLog("No delete handler, aborting.");
    } else {
      debugLog("Delete dialog options:", newDialogOptions);
      setDialogOptions(newDialogOptions);
    }
  };

  const handleDeleteConfirm = async () => {
    debugLog("handleDeleteConfirm:", dialogOptions);
    if (!dialogOptions.itemToDelete || !dialogOptions.onDelete) return;
    await dialogOptions.onDelete();
  };


  // HANDLE EDIT MODEL
  const handleEditModel = async () => {
    const modelId = model.Id;
    debugLog("handleEditModel:", modelId);
    const params: any = await getModel(modelId);
    if (params.Id) {
      params.Contributor = params.Contributor ? params.Contributor : ContribUser;
      params.ContributorOrganization = params.ContributorOrganization ? params.ContributorOrganization : ContribOrg;
      onEditModel(modelId, params as Partial<CreateDataModelParams>);
    } else { alertDialog('Edit Model Dialog', 'Unable to get model parameters at this time.'); }
  };

  // HANDLE DOWNLOAD WITH TOAST ERROR HANDLING
  const handleDownloadWithToast = async (id: number, type?: string, pub?: boolean) => {
    try {
      await downloadOpenApiSchema(id, type, pub);
      showToast("File downloaded successfully", 'success');
    } catch (e) {
      // console.log("Failed to download OpenApi Schema file", e);
      showToast(errorToString(e), 'error');
    }
  };


  // HANDLE SELECT DIALOG
  const getSelectDialogOptions = async (type: "entity" | "attribute" | "valueSet", idFilter: any[]) => {
    try {
      // What types of models to pull data from
      let selectedTypes: string[] = [];
      switch (model.Type) {
        case "OrgLIF": selectedTypes = ["OrgLIF", "BaseLIF", "PartnerLIF"]; break;
        case "PartnerLIF": selectedTypes = ["PartnerLIF", "BaseLIF"]; break;
        case "BaseLIF":
        case "SourceSchema":
          break;
        default: reportWarn('Unfamiliar model type', model.Type); return;
      }
      // Get models we will build from
      const CheckAllTypes = !!selectedTypes.length;
      const allModels = CheckAllTypes ? await listModels() : [];
      const models = CheckAllTypes ? allModels?.filter((m: any) => selectedTypes.includes(m.Type)) : [model];
      debugLog(`Building SelectDialog ${capitalize(type)} options for ${models.length} models of type(s) ${selectedTypes.join(', ')}`);
      // Build select options from specified models
      let opts: any[] = [];
      const uniqueIds = new Set();
      const listFunc = type === "entity" ? listEntitiesForDataModel : (type === "attribute" ? listAttributesForDataModel : listValueSetsForDataModel);
      let modelDataResults = await Promise.all(
        models.map(async (m: any) => {
          const fromModel: any[] = await listFunc(m.Id);
          debugLog(` - Model ${m.Id} (${m.Name}) has ${fromModel?.length || 0} ${type}`);
          return fromModel.filter((i: any) => {
            if (!i.Id || uniqueIds.has(i.Id) || idFilter.includes(i.Id)) return false;
            uniqueIds.add(i.Id);
            return true;
          });
        })
      );
      // Flatten all results into single arrays and sort
      modelDataResults = modelDataResults.flatMap((r: any) => r);
      // debugLog(` - Compiled results:`, modelDataResults);
      opts = modelDataResults.sort((a: any, b: any) => a.Name.localeCompare(b.Name));
      debugLog(' - Total, unique SelectDialog options:', opts.length);
      return opts;
    } catch (error) {
      reportError("Error building SelectDialog options:", errorToString(error));
    }
  };

  const handleSelectDialog = async (node: any, kind: string, pathToNode: any) => {
    debugLog("handleSelectDialog:", kind, node, pathToNode);
    if (!['entity', 'attribute', 'valueSet'].includes(kind)) {
      alertDialog("Select Dialog Error", `Unhandled select dialog type '${kind}' for ${node.type}#${node.id}.`);
      return;
    }
    // Determine IDs to filter out from selection options
    let idFilter: number[] = [];
    if (kind === "entity") { // Exclude parents, children, and current entity
      idFilter = [...pathToNode.map((n: any) => n.id).filter(Boolean),
        ...selectedModel.EntityAssociations.filter((ea: any) =>
          !ea.Deleted && ea.ParentEntityId === node.id
          && (!ea.ExtendedByDataModelId || ea.ExtendedByDataModelId === model.Id)
        ).map((ea: any) => ea.ChildEntityId),
        ...(baseModel?.EntityAssociation || []).filter((ea: any) =>
          !ea.Deleted && ea.ParentEntityId === node.id
          && (!ea.ExtendedByDataModelId || ea.ExtendedByDataModelId === 1)
        ).map((ea: any) => ea.ChildEntityId)
      ];
    } else if (kind === "attribute") { // Exclude already associated attributes
      const entityId = node.type === 'entity' ? node.id : null;
      if (!entityId) { reportError("Only entities can have attributes:", node); return; }
      idFilter = [
        ...(await listAttributesByEntity(entityId, model.Id)).map((a: any) => a.Id),
        ...(baseModel ? (await listAttributesByEntity(entityId, 1)).map((a: any) => a.Id) : [])
      ];
    }
    idFilter = [...new Set(idFilter)].filter(Boolean); // unique and valid IDs
    debugLog(" > Filtering out the following IDs from options:", idFilter);
    // Get select options and create dialog options
    const selectOpts = await getSelectDialogOptions(kind as "entity" | "attribute" | "valueSet", idFilter);
    if (!selectOpts?.length) {
      alertDialog('No Existing Options', 'No available options to select found. Try again later or add a new one.');
      return;
    }
    const capitalKind = capitalize(kind);
    const selectDialogOptions: any = {
      isOpenSelectDialog: true,
      type: capitalKind,
      itemToEdit: {Id: node.id, Name: node.label, Type: node.type},
      selectOptions: selectOpts,
    };
    switch(kind) {
      case "entity":
        selectDialogOptions.fields = entityAssociationFields(model);
        selectDialogOptions.onEdit = async (id: number, selected: any, params: any) => {
          let newParams = tmplCreateEntityAssociation(id, model);
          newParams = updateObjAWithB(newParams, params || {});
          newParams.ChildEntityId = selected;
          debugLog(`Updating ${node.type}#${id}:`, selected, newParams);
          try {
            const resp: any = await createEntityAssociation(newParams);
            if (resp?.Id) {
              debugLog(">> Created Entity Association:", resp?.Id);
              const incExists = selectedModel?.Inclusions?.find(
                (inc: any) => inc.IncludedElementId === selected && inc.ElementType === 'Entity' && !inc.Deleted
              );
              if (useInclusion && !incExists) {
                let inclusionParams = tmplCreateInclusion(model.Id, selected, 'Entity');
                inclusionParams = updateObjAWithB(inclusionParams, params || {});
                const incResp: any = await createInclusion(inclusionParams);
                if (incResp?.Id) debugLog(">> Created Inclusion for Entity Association:", incResp?.Id);
              }
              await fetchData();
            }
          } catch (error) { reportError("Error creating entity association:", errorToString(error)); }
        };
        break;
      case "attribute":
        selectDialogOptions.fields = attributeAssociationFields(model);
        selectDialogOptions.onEdit = async (id: number, selected: any, params: any) => {
          let newParams = tmplCreateEntityAttributeAssociation(id, model);
          newParams = updateObjAWithB(newParams, params || {});
          newParams.AttributeId = selected;
          debugLog(`Updating ${node.type}#${id}:`, selected, newParams);
          try {
            const resp: any = await createEntityAttributeAssociation(newParams);
            if (resp?.Id) {
              debugLog(">> Created Attribute Association:", resp?.Id);
              const incExists = selectedModel?.Inclusions?.find(
                (inc: any) => inc.IncludedElementId === selected && inc.ElementType === 'Attribute' && !inc.Deleted
              );
              if (useInclusion && !incExists) {
                let inclusionParams = tmplCreateInclusion(model.Id, selected, 'Attribute');
                inclusionParams = updateObjAWithB(inclusionParams, params || {});
                const incResp: any = await createInclusion(inclusionParams);
                if (incResp?.Id) debugLog(">> Created Inclusion for Attribute Association:", incResp?.Id);
              }
              await fetchData();
            }
          } catch (error) { reportError("Error creating entity association:", errorToString(error)); }
        };
        break;
      case "valueSet":
        selectDialogOptions.onEdit = async (id: number, selected: any) => {
          const params = {ValueSetId: selected} as AttributeParams;
          debugLog(`Updating ${node.type}#${id}:`, params);
          try {
            const resp: any = await updateAttribute(id, params);
            if (resp?.Id) {
              await fetchData();
            }
          } catch (error) { reportError("Error creating entity association:", errorToString(error)); }
        };
        break;
      default: reportWarn("Unhandled type in Select Dialog:", node); break;
    }
    if (!selectDialogOptions.onEdit) {
      debugLog("No edit handler, aborting.");
    } else {
      debugLog("Select dialog options:", selectDialogOptions);
      setDialogOptions(selectDialogOptions);
    }
  };


  // handleCheckboxToggle(node, field, value[, updFetch])
  const handleCheckboxToggle = async (n: any, f: string, v: boolean, u: boolean = true) => {
    debugLog(`handleCheckboxToggle: ${capitalize(n?.type)}_${n?.id} setting '${f}' to ${v}`);
    if (f === "pub") await cbTogglePublic(n, v, u);
    else if (f === "inc") await cbToggleInclude(n, v, u);
    else reportWarn("Unhandled checkbox field:", f);
  };

  const cbTogglePublic = async (n: any, v: boolean, updFetch: boolean = true) => {
    if (!n) return;
    else if (!useInclusion) { reportWarn("Inclusions not used for this model"); return; }
    else if (!n.include) { reportWarn("Cannot toggle public for non-included node"); return; }
    const inclusion = selectedModel?.Inclusions?.find(
      (inc: any) => inc.IncludedElementId === n.id && inc.ElementType === capitalize(n.type) && !inc.Deleted
    )
    const inclusionId = inclusion?.Id || null;
    if (!inclusionId) { reportError("Inclusion record not found for node:", n.id, n); return; }
    debugLog(`Toggling Inclusion_${inclusionId} Access for node:`, n.id, " => ", v, "; fetchData():", updFetch);
    const params = { LevelOfAccess: v ? 'Public' : 'Private' } as CreateInclusionParams;
    try {
      const resp: any = await updateInclusion(inclusionId, params);
      if (resp?.Id) {
        debugLog(`>> Updated ${capitalize(n.type)}_${n.id} Public access updated to ${v}`);
        if (updFetch) await fetchData();
        else { // update local state
          selectedModel.Inclusions.forEach((inc: any) => {
            if (inc.Id === inclusionId) inc.LevelOfAccess = v ? 'Public' : 'Private';
          });
        }
      }
    } catch (error) {
      reportError("Error toggling public:", errorToString(error));
    }
  };

  const cbToggleInclude = async (n: any, v: boolean, updFetch: boolean = true) => {
    if (!n) return;
    else if (!useInclusion) { reportWarn("Inclusions not used for this model"); return; }
    else if (!["entity", "attribute"].includes(n.type)) { reportWarn("Cannot toggle include for unsaved node:", n); return; }
    const ShouldExist = !v;
    const inclusion = selectedModel?.Inclusions?.find(
      (inc: any) => inc.IncludedElementId === n.id && inc.ElementType === capitalize(n.type) && !inc.Deleted
    );
    const inclusionId = inclusion?.Id || null;
    debugLog(`Toggling Include_${inclusionId || "NEW"} for node:`, n.id, " => ", v, "; fetchData():", updFetch);
    if (!ShouldExist) {
      try { // POST
        const newInclusionParams = tmplCreateInclusion(model.Id, n.id, capitalize(n.type));
          newInclusionParams.Contributor = ContribUser || "";
          newInclusionParams.ContributorOrganization = ContribOrg || "";
        const resp: any = await createInclusion(newInclusionParams);
        if (resp?.Id) {
          debugLog(`>> Added Inclusion for ${capitalize(n.type)}_${n.id}`);
          if (updFetch) await fetchData();
          else { // add to local state
            selectedModel.Inclusions.push(resp);
          }
        }
      } catch (error) { reportError("Error creating inclusion:", errorToString(error)); }
    } else {
      try { // DELETE
        const resp: any = await deleteInclusion(inclusionId);
        debugLog("Delete inclusion resp:", resp);
        if (resp?.ok) {
          debugLog("Deleted inclusion:", resp);
          if (updFetch) await fetchData();
          else { // remove from local state
            selectedModel.Inclusions = selectedModel.Inclusions.filter((inc: any) => inc.Id !== inclusionId);
          }
        }
      } catch (error) { reportError("Error deleting inclusion:", errorToString(error)); }
    }
  };


  const [propBtns, setPropBtns] = useState<any>({});
  useEffect(() => {
    if (!selectedNode || !Object.keys(selectedNode).length) { setPropBtns({}); return; }
    const validAssoc = selectedNode.hasAssocId && ['entity', 'attribute'].includes(selectedNode.type);
    let newOpts: any = {
      inc: selectedNode.hasIncId && !selectedNode.isRef,
      assocEdit: validAssoc && (!selectedNode.isRef || selectedNode.isRef !== "c"),
      assocDel: (validAssoc && (!selectedNode.isRef || selectedNode.isRef !== "c")) || selectedNode.type === "valueSet",
      reg: !selectedNode.isRef,
    };
    newOpts.div1 = (newOpts.inc && (newOpts.reg || (newOpts.assocEdit || newOpts.assocDel)));
    newOpts.div2 = (newOpts.reg && (newOpts.assocEdit || newOpts.assocDel));
    setPropBtns(newOpts);
  }, [selectedNode]);

  const colPropRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!colPropRef?.current) return;
    colPropRef.current.scrollTo({ top: 0, behavior: "smooth" });
  }, [propDetails]);

  const treeData = useMemo(() => {
    if (loading || !selectedModel) return [];
    return transformData(selectedModel, baseModel) || [];
  }, [loading]);
  useEffect(() => { fetchData(); }, [fetchData]);
  
  return (
    <>
      <Dialog.Root>
        <Box className={`col-layout column-model ${loading ? "pending" : "loaded"}`}>
          <div className="data-loading">
            <h2 className="col-head">Loading...</h2>
            <div className="col-body">
              <p>Please wait while we process your request.</p>
              <p className="spinner">
                <Spinner style={{ width: "3em", height: "3em" }} />
              </p>
            </div>
          </div>
          <TreeModelExplorer
            data={treeData}
            // showModelAsRoot
            searchFilter
            onEditModel={handleEditModel}
            onAddNew={handleOnAddNew}
            onFuncDownload={handleDownloadWithToast}
            headerString={treeHeader}
            triggerModal={async (n, k, s) => { await s ? handleSelectDialog(n, k, s) : handleCreateDropdown(n, k); }}
            triggerCheckbox={async (n, f, v) => { await handleCheckboxToggle(n, f, v, false); }}
            typeHandlers={{
              model: (n: any, p?: any) => { onNodeSelect(n, p); onModelSelect(); },
              entity: (n: any, p?: any) => { onNodeSelect(n, p); onEntitySelect(n?.id); },
              attribute: (n: any, p?: any) => { onNodeSelect(n, p); onAttributeSelect(n?.id); },
              valueSet: (n: any, p?: any) => { onNodeSelect(n, p); onValueSetSelect(n?.id, true); },
              value: (n: any, p?: any) => { onNodeSelect(n, p); onValueSelect(n?.id, n?.parentId); },
            }}
            showPublicToggles={showPublicToggles}
            showInclusionToggles={showInclusionToggles}
          />
        </Box>
        {selectedModel && propDetails && (
          <Box className={"col-layout column-properties"} ref={colPropRef}>
            <Box flexGrow={"1"}>
              <h2 className="col-head" style={{display: "flex", alignItems: "center", gap: "8px"}}>
                <div>{selectedType} Properties</div>
                <div style={{ marginLeft: "auto", display: "flex", gap: "12px" }}>
                  {selectedNode && propDetails.Id > 0 && (
                  <div className="actions">
                    {propBtns?.inc && (
                    <button className="rt-reset rt-BaseButton rt-r-size-1 rt-variant-ghost" style={{color: "#00008B"}}
                      aria-label="Edit Inclusion" title="Edit Inclusion" onClick={handleEditInclusion(selectedNode)}><CardStackMinusIcon /></button>
                    )}
                    {propBtns?.div1 && (<DashIcon />)}
                    {propBtns?.assocEdit && (
                    <button className="rt-reset rt-BaseButton rt-r-size-1 rt-variant-ghost" style={{color: "#00008B"}}
                      aria-label="Edit Association" title="Edit Association" onClick={handleEditAssoc(selectedNode)}><FileTextIcon /></button>
                    )}
                    {propBtns?.assocDel && (
                    <button className="rt-reset rt-BaseButton rt-r-size-1 rt-variant-ghost" style={{color: "#cc2200"}}
                      aria-label="Remove Association" title="Remove Association" onClick={handleDeleteItem(propDetails, true)}><LinkBreak2Icon /></button>
                    )}
                    {propBtns?.div2 && (<DashIcon />)}
                    {propBtns?.reg && (
                    <>
                    <button className="rt-reset rt-BaseButton rt-r-size-1 rt-variant-ghost" style={{color: "#00008B"}}
                      aria-label="Edit Item" title="Edit Item" onClick={handleEditItem(propDetails)}><Pencil2Icon /></button>
                    <button className="rt-reset rt-BaseButton rt-r-size-1 rt-variant-ghost" style={{color: "#cc2200"}}
                      aria-label="Delete Item" title="Delete Item" onClick={handleDeleteItem(propDetails, false)}><TrashIcon /></button>
                    </>
                    )}
                  </div>
                  )}
                </div>
              </h2>
              <div className="col-body">
                <ObjectDetails card={false} orient="vertical" object={propDetails} />
              </div>
            </Box>
          </Box>
        )}
      </Dialog.Root>

      <CrudDialog
        isOpen={isCrudDialogOpen}
        onOpenChange={handleDialogOpenChange}
        title={dialogOptions.title}
        fields={dialogOptions.fields || []}
        onCreate={dialogOptions.onCreate}
        isEditMode={!!dialogOptions.isEditMode}
        itemToEdit={dialogOptions.itemToEdit}
        onEdit={dialogOptions.onEdit}
      />

      <SelectDialog
        isOpen={!!dialogOptions.isOpenSelectDialog}
        onOpenChange={() => setDialogOptions({})}
        type={dialogOptions.type}
        itemList={dialogOptions.selectOptions}
        itemToEdit={dialogOptions.itemToEdit}
        fields={dialogOptions.fields || []}
        onEdit={dialogOptions.onEdit}
      />

      <DeleteDialog
        isOpen={!!dialogOptions.itemToDelete}
        onClose={() => setDialogOptions({})}
        title={dialogOptions.title}
        message={dialogOptions.message}
        onConfirm={handleDeleteConfirm}
      />

      <SimpleAlertDialog
        isOpen={!!dialogOptions.alertDialog}
        onClose={() => setDialogOptions({})}
        title={dialogOptions.title}
        message={dialogOptions.message}
      />
    </>
  );
};

export default ModelTree;
